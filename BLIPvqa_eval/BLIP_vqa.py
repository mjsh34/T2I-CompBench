import argparse
import os
from pathlib import Path

import torch

from tqdm import tqdm, trange


import json
from tqdm.auto import tqdm
import sys
import spacy
from PIL import Image, ExifTags

from BLIP.train_vqa_func import VQA_main

def Create_annotation_for_BLIP(image_folder, outpath, np_index=None):
    nlp = spacy.load("en_core_web_sm")

    annotations = []
    file_names = os.listdir(image_folder)
    file_names.sort(key=lambda x: int(x.split("_")[-1].split('.')[0]))#sort


    cnt=0

    #output annotation.json
    for file_name in file_names:
        image_dict={}
        image_dict['image'] = image_folder+file_name
        image_dict['question_id']= cnt
        #f = file_name.split('_')[0]
        f = get_caption(os.path.join(image_folder, file_name))
        doc = nlp(f)
        
        noun_phrases = []
        for chunk in doc.noun_chunks:
            if chunk.text not in ['top', 'the side', 'the left', 'the right']:  # todo remove some phrases
                noun_phrases.append(chunk.text)
        if(len(noun_phrases)>np_index):#句子的np小于np_index
            q_tmp = noun_phrases[np_index]
            image_dict['question']=f'{q_tmp}?'
        else:
            image_dict['question'] = ''
            

        image_dict['dataset']="color"
        cnt+=1

        annotations.append(image_dict)

    print('Number of Processed Images:', len(annotations))

    json_file = json.dumps(annotations)
    with open(f'{outpath}/color_test.json', 'w') as f:
        f.write(json_file)

def parse_args():
    parser = argparse.ArgumentParser(description="BLIP vqa evaluation.")
    parser.add_argument(
        "--out_dir",
        type=str,
        default=None,
        required=True,
        help="Path to output BLIP vqa score",
    )
    parser.add_argument(
        "--np_num",
        type=int,
        default=8,
        help="Noun phrase number, can be greater or equal to the actual noun phrase number",
    )
    args = parser.parse_args()
    return args

def get_caption(image_fp):
    if "CAPTIONTOOLONG_" in Path(image_fp).stem:
        img_pil = Image.open(image_fp)
        caption = img_pil.getexif()[list(ExifTags.TAGS.keys())[list(ExifTags.TAGS.values()).index('UserComment')]]
    else:
        caption = Path(image_fp).stem.split('_')[0]
    return caption

def main():
    args = parse_args()

    out_dir = args.out_dir
    images_dir = f"{out_dir}/samples/"
    noun_chunks_d = {}

    nlp = spacy.load("en_core_web_sm")
    for img_fn in tqdm(os.listdir(images_dir)):
        caption = get_caption(os.path.join(images_dir, img_fn))
        doc = nlp(caption)
        nc_list = list(doc.noun_chunks)
        noun_chunks_d[img_fn] = nc_list

    if args.np_num > 0:
        np_index = args.np_num #how many noun phrases
    else:
        max_nclist_size = max(map(len, noun_chunks_d.values()))
        np_index = max_nclist_size

    answer = []
    sample_num = len(os.listdir(os.path.join(args.out_dir,"samples")))
    reward = torch.zeros((sample_num, np_index)).to(device='cuda')

    order="_blip" #rename file
    for i in tqdm(range(np_index)):
        print(f"start VQA{i+1}/{np_index}!")
        os.makedirs(f"{out_dir}/annotation{i + 1}{order}", exist_ok=True)
        os.makedirs(f"{out_dir}/annotation{i + 1}{order}/VQA/", exist_ok=True)
        Create_annotation_for_BLIP(
            f"{out_dir}/samples/",
            f"{out_dir}/annotation{i + 1}{order}",
            np_index=i,
        )
        answer_tmp = VQA_main(f"{out_dir}/annotation{i + 1}{order}/",
                              f"{out_dir}/annotation{i + 1}{order}/VQA/")
        answer.append(answer_tmp)

        with open(f"{out_dir}/annotation{i + 1}{order}/VQA/result/vqa_result.json", "r") as file:
            r = json.load(file)
        with open(f"{out_dir}/annotation{i + 1}{order}/color_test.json", "r") as file:
            r_tmp = json.load(file)
        for k in range(len(r)):
            if(r_tmp[k]['question']!=''):
                reward[k][i] = float(r[k]["answer"])
            else:
                reward[k][i] = 1
        print(f"end VQA{i+1}/{np_index}!")
    reward_final = reward[:,0]
    for i in range(1,np_index):
        reward_final *= reward[:,i]

    #output final json
    with open(f"{out_dir}/annotation{i + 1}{order}/VQA/result/vqa_result.json", "r") as file:
        r = json.load(file)
    reward_after=0
    for k in range(len(r)):
        r[k]["answer"] = '{:.4f}'.format(reward_final[k].item())
        reward_after+=float(r[k]["answer"])
    os.makedirs(f"{out_dir}/annotation{order}", exist_ok=True)
    with open(f"{out_dir}/annotation{order}/vqa_result.json", "w") as file:
        json.dump(r, file)

    # calculate avg of BLIP-VQA as BLIP-VQA score
    print("BLIP-VQA score:", reward_after/len(r),'!\n')
    with open(f"{out_dir}/annotation{order}/blip_vqa_score.txt", "w") as file:
        file.write("BLIP-VQA score:"+str(reward_after/len(r)))



if __name__ == "__main__":
    main()
