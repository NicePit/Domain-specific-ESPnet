import json
import logging
import os
from pathlib import Path

from tqdm import tqdm

from dataset_utils.base_transformer import AbstractDataTransformer

SUBSET_SIZE = os.environ.get("ESPNET_SUBSET_SIZE", None)
logger = logging.root


class GongSpanish2KaldiTransformer(AbstractDataTransformer):

    def __init__(self):
        super().__init__()
        self._prefix = 'gong'
        self.overall_duration = 0
        if SUBSET_SIZE:
            self.SUBSET_SIZE = int(SUBSET_SIZE)

    def transform(self, raw_data_path, espnet_kaldi_eg_directory, *args, **kwargs):

        raw_data_path = os.path.join(raw_data_path, 'to-y-data', 'spanish_test_set')
        self.kaldi_data_dir = os.path.join(espnet_kaldi_eg_directory, 'data')
        kaldi_audio_files_dir = os.path.join(espnet_kaldi_eg_directory, 'downloads')

        # copy audio files to separate directory according to kaldi directory conventions
        logger.info("Copying files to kaldi download directory")

        transcripts_dir = os.path.join(raw_data_path, 'spanish_human_manual_transcription')
        transcript_paths = list(os.walk(transcripts_dir))[0][2]
        texts = []
        chunks = []
        cut_audio_paths = []
        for transcript_path in tqdm(transcript_paths):
            try:
                cur_texts, cur_chunks, cur_cut_audio_paths = self.cut_audio_to_monologues(raw_data_path,
                                                                                          transcript_path)
                texts.extend(cur_texts)
                chunks.extend(cur_chunks)
                cut_audio_paths.extend(cur_cut_audio_paths)
            except Exception as e:
                logger.error(f"EXCEPTION {e}")
        print('Total dataset duration, hours:', self.overall_duration / 3600)

        best_monologue_indexes = [idx for idx, chunk in enumerate(chunks) if chunk[2] > 3
                                  and "<unk>" not in texts[idx]
                                  and "+" not in chunk[3]
                                  and len(texts[idx]) > 0]
        texts = [texts[idx] for idx in best_monologue_indexes]
        cut_audio_paths = [cut_audio_paths[idx] for idx in best_monologue_indexes]
        speakers = [chunks[idx][3] for idx in best_monologue_indexes]
        origin_audio_dir = [os.path.join(raw_data_path, 'cut_audio')]
        destination_audio_dir = os.path.join(kaldi_audio_files_dir, self.prefix)
        self.copy_audio_files_to_kaldi_dir(origin_paths=origin_audio_dir,
                                           destination_path=destination_audio_dir)

        wavscp, text, utt2spk = self.generate_arrays(texts, speakers, cut_audio_paths)

        logger.info(f"Total dataset size: {len(text)}")
        if len(text) < self.SUBSET_SIZE:
            logger.info(
                f"ATTENTION! Provided subset size ({self.SUBSET_SIZE}) is less than overall dataset size ({len(text)}). "
                f"Taking all dataset")
        if self.SUBSET_SIZE:
            logger.info(f"Subset size: {self.SUBSET_SIZE}")
            wavscp = wavscp[:self.SUBSET_SIZE]
            text = text[:self.SUBSET_SIZE]
            utt2spk = utt2spk[:self.SUBSET_SIZE]

        logger.info("Splitting train-test")
        wavscp_train, wavscp_test, text_train, text_test, utt2spk_train, utt2spk_test = \
            self.split_train_test(wavscp,
                                  text,
                                  utt2spk)

        self.create_files(wavscp_train, text_train, utt2spk_train, 'train')
        self.create_files(wavscp_test, text_test, utt2spk_test, 'test')

    def cut_audio_to_monologues(self, relative_path, transcript_path):
        json_path = os.path.join(relative_path, 'spanish_human_manual_transcription', transcript_path)
        wav_path = f"{transcript_path[:-5]}.raw-audio.wav"
        with open(json_path, 'r') as f:
            try:
                data = json.load(f)
            except:
                logger.error("ERROR IN JSON READING")
            self.overall_duration += data['monologues'][-1]['end']
            chunks = [
                (
                    utterance['start'], utterance['end'], utterance['end'] - utterance['start'],
                    utterance['speaker']['id'])
                for utterance in
                data['monologues']]
            texts = [" ".join([_['text'].encode('cp1252').decode() for _ in utterance['terms']]) for utterance in
                     data['monologues']]
            assert len(chunks) == len(
                texts), "Length of texts is not equal to length of chunks in the transcript file"
            cut_audio_paths = self.cut_audio_to_chunks(base_dir=relative_path,
                                                       unprocessed_dir_prefix='audio',
                                                       processed_dir_prefix='cut_audio',
                                                       wav_path=wav_path, chunks=chunks)
            return texts, chunks, cut_audio_paths

    def generate_arrays(self, origin_texts, speakers, audio_paths):
        wavscp = list()
        text = list()
        utt2spk = list()

        for idx, transcript in enumerate(origin_texts):
            tokens = transcript.lower().split(' ')
            transcript = ' '.join(tokens[:-1])

            file_path = audio_paths[idx]
            utt_id = idx + 1
            speaker_id = self.prefix + 'sp' + ''.join(speakers[idx])
            utterance_id = f'{speaker_id}-{self.prefix}{utt_id}'
            wavscp.append(f'{utterance_id} {file_path}')
            utt2spk.append(f'{utterance_id} {speaker_id}')
            text.append(f'{utterance_id} {transcript}')

        return wavscp, text, utt2spk
