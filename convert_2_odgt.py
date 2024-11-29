import os
import glob

labels_dir_path = 'Labels/2fps'
odgt_file_path = 'Labels/hanwha_QNF-8010_wallmount.odgt'

txt_files = glob.glob(os.path.join(labels_dir_path, "*.txt"))
txt_files.sort()

annotations = []
for txt_file in txt_files:
    with open (txt_file, 'r') as file:
        anno = file.read()
        annotations.append(anno)


with open(odgt_file_path, 'w') as file:
    for annotation in annotations:
        file.write(annotation + '\n')

