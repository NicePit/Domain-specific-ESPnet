import os
from pathlib import Path
from pydub import AudioSegment
from tqdm import tqdm
import pandas as pd
from multiprocessing import Pool

from .base_transformer import AbstractKaldiDataTransformer


class CommonVoiceKaldiTransformer(AbstractKaldiDataTransformer):

    def transform(self, raw_data_path, espnet_kaldi_eg_directory, subset_size=None, *args, **kwargs):

        self.kaldi_data_dir = os.path.join(espnet_kaldi_eg_directory, 'data')
        kaldi_audio_files_dir = os.path.join(espnet_kaldi_eg_directory, 'downloads')
        origin_audiofiles_dir = os.path.join(raw_data_path, 'clips')

        data = pd.read_csv(Path(raw_data_path, 'validated.tsv'), delimiter='\t')
        dataset_size = data.shape[0]

        print("Total dataset size", dataset_size)

        if subset_size:
            print("Subset size:", subset_size)
            if dataset_size < subset_size:
                print(
                    f"ATTENTION! Provided subset size ({subset_size}) is less "
                    f"than overall dataset size ({dataset_size}). "
                    f"Taking all dataset")
            self.SUBSET_SIZE = subset_size
            data = data[:subset_size]

        audio_files = data['path'].tolist()
        if os.path.exists(kaldi_audio_files_dir):
            pass
        else:
            os.makedirs(kaldi_audio_files_dir)
        print("Transforming audio to .wav and copying to eg directory")
        list_of_files = list()
        for file in tqdm(audio_files):
            joined_path = os.path.join(origin_audiofiles_dir, file)
            list_of_files.append(joined_path)
        p = Pool(processes=os.cpu_count())
        p.map(self.convert_to_wav_from_mp3, list_of_files)

        print("Generating train and test files")

        wavscp, text, utt2spk = self.generate_arrays(data)

        wavscp_train, wavscp_test, text_train, text_test, utt2spk_train, utt2spk_test = \
            self.split_train_test(wavscp,
                                  text,
                                  utt2spk,
                                  test_proportion=0.2)

        self.create_files(wavscp_train, text_train, utt2spk_train, os.path.join(kaldi_data_dir, 'train'))
        self.create_files(wavscp_test, text_test, utt2spk_test, os.path.join(kaldi_data_dir, 'test'))

    def convert_to_wav_from_mp3(self, source_path: str, destination_folder: str):
        # print("source_path", source_path)
        # print("source_path absolute", Path(source_path).absolute())
        new_file_name = source_path.split("/")[-1][:-4] + '.wav'
        # print("new file name", new_file_name)

        sound = AudioSegment.from_mp3(source_path)
        # print("source file loaded", source_path)

        destination_path = Path(destination_folder, new_file_name)
        # print("destination path", destination_path)

        sound.export(destination_path, format="wav")
        # print("export to wav successful", destination_path)

    def generate_arrays(self, data: pd.DataFrame):

        wavscp = list()
        text = list()
        utt2spk = list()

        data['path'] = data['path'].apply(lambda x: "downloads/" + x[:-4] + '.wav')

        for idx, row in data.iterrows():
            transcript = self.clean_text(row['sentence'])
            file_path = row['path']
            # speaker_id = row['client_id']
            speaker_id = f'speaker_{idx}'
            segment_id = f'segment_{idx}'
            utterance_id = f'utterance{speaker_id}-{segment_id}'
            wavscp.append(f'{utterance_id} {file_path}')
            utt2spk.append(f'{utterance_id} {speaker_id}')
            text.append(f'{utterance_id} {transcript}')

        return wavscp, text, utt2spk