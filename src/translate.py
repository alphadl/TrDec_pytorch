from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import _pickle as pickle
import shutil
import gc
import os
import sys
import time

import numpy as np

from data_utils import DataLoader
from hparams import *
from utils import *
from models import *
from trdec import *
from tree_utils import *

import torch
import torch.nn as nn
from torch.autograd import Variable

class TranslationHparams(HParams):
  dataset = "Translate dataset"

parser = argparse.ArgumentParser(description="Neural MT translator")

add_argument(parser, "trdec", type="bool", default=False, help="whether to use tree model or not")
add_argument(parser, "cuda", type="bool", default=False, help="GPU or not")
add_argument(parser, "data_path", type="str", default=None, help="path to all data")
add_argument(parser, "model_dir", type="str", default="outputs", help="root directory of saved model")
add_argument(parser, "source_test", type="str", default=None, help="name of source test file")
add_argument(parser, "target_test", type="str", default=None, help="name of target test file")
add_argument(parser, "target_tree_test", type="str", default=None, help="name of target test parse file")
add_argument(parser, "beam_size", type="int", default=None, help="beam size")
add_argument(parser, "max_len", type="int", default=300, help="maximum len considered on the target side")
add_argument(parser, "non_batch_translate", type="bool", default=False, help="use non-batched translation")
add_argument(parser, "batch_size", type="int", default=32, help="")
add_argument(parser, "merge_bpe", type="bool", default=True, help="")
add_argument(parser, "source_vocab", type="str", default=None, help="name of source vocab file")
add_argument(parser, "target_vocab", type="str", default=None, help="name of target vocab file")
add_argument(parser, "target_tree_vocab", type="str", default=None, help="name of target vocab file")
add_argument(parser, "target_word_vocab", type="str", default=None, help="name of target vocab file")
add_argument(parser, "n_train_sents", type="int", default=None, help="max number of training sentences to load")
add_argument(parser, "out_file", type="str", default="trans", help="output file for hypothesis")
add_argument(parser, "debug", type="bool", default=False, help="output file for hypothesis")


args = parser.parse_args()

model_file_name = os.path.join(args.model_dir, "model.pt")
model = torch.load(model_file_name)
model.eval()

out_file = os.path.join(args.model_dir, args.out_file)
if args.trdec:
  out_parse_file = os.path.join(args.model_dir, args.out_file+".parse")

hparams = TranslationHparams(
  data_path=args.data_path,
  source_vocab=args.source_vocab,
  target_vocab=args.target_vocab,
  source_test = args.source_test,
  target_test = args.target_test,
  target_tree_test = args.target_tree_test,
  cuda=args.cuda,
  beam_size=args.beam_size,
  max_len=args.max_len,
  batch_size=args.batch_size,
  n_train_sents=args.n_train_sents,
  merge_bpe=args.merge_bpe,
  out_file=out_file,
  trdec=args.trdec,
  target_tree_vocab=args.target_tree_vocab,
  target_word_vocab=args.target_word_vocab,
)

hparams.add_param("filtered_tokens", set([model.hparams.pad_id, model.hparams.eos_id, model.hparams.bos_id]))
hparams.add_param("pad_id", model.hparams.pad_id)
hparams.add_param("bos_id", model.hparams.bos_id)
hparams.add_param("eos_id", model.hparams.eos_id)
hparams.add_param("unk_id", model.hparams.unk_id)
model.hparams.cuda = hparams.cuda
data = DataLoader(hparams=hparams, decode=True)
if args.debug:
  hparams.add_param("target_word_vocab_size", data.target_word_vocab_size)
  hparams.add_param("target_rule_vocab_size", data.target_rule_vocab_size)
  crit = get_criterion(hparams)

out_file = open(hparams.out_file, 'w', encoding='utf-8')
if args.trdec:
  out_parse_file = open(out_parse_file, 'w', encoding='utf-8')

end_of_epoch = False
num_sentences = 0

x_test = data.x_test.tolist()
if args.debug:
  y_test = data.y_test.tolist()
else:
  y_test = None
#print(x_test)
if args.trdec:
  hyps, scores = model.translate(
        x_test, target_rule_vocab=data.target_tree_vocab,
        beam_size=args.beam_size, max_len=args.max_len, y_label=y_test)
else:
  hyps = model.translate(
        x_test, beam_size=args.beam_size, max_len=args.max_len)

if args.debug:
  forward_scores = []
  while not end_of_epoch:
    ((x_test, x_mask, x_len, x_count),
     (y_test, y_mask, y_len, y_count),
     batch_size, end_of_epoch) = data.next_test(test_batch_size=hparams.batch_size, sort_by_x=True)
  
    num_sentences += batch_size
    logits = model.forward(x_test, x_mask, x_len, y_test[:,:-1,:], y_mask[:,:-1], y_len, y_test[:,1:,2])
    logits = logits.view(-1, hparams.target_rule_vocab_size+hparams.target_word_vocab_size)
    labels = y_test[:,1:,0].contiguous().view(-1)
    val_loss, val_acc, rule_loss, word_loss, eos_loss, rule_count, word_count, eos_count =  \
        get_performance(crit, logits, labels, hparams)
    #print("train forward:", val_loss.data)
    #print("train label:", labels.data)
    #logit_score = []
    #for i,l in enumerate(labels): logit_score.append(logits[i][l].data[0])
    #print("train_logit", logit_score)
    #print("train_label", labels)
    forward_scores.append(val_loss.sum().data[0])
    # The normal, correct way:
    #hyps = model.translate(
    #      x_test, x_len, beam_size=args.beam_size, max_len=args.max_len)
    # For debugging:
    # model.debug_translate_batch(
    #   x_test, x_mask, x_pos_emb_indices, hparams.beam_size, hparams.max_len,
    #   y_test, y_mask, y_pos_emb_indices)
    # sys.exit(0)
  print("translate_score:", sum(scores))
  print("forward_score:", sum(forward_scores))
  exit(0)
for h in hyps:
  if args.trdec:
    deriv = []
    for w in h:
      if w < data.target_word_vocab_size:
        deriv.append([data.target_word_vocab[w], False])
      else:
        deriv.append([data.target_tree_vocab[w], False])
    tree = Tree.from_rule_deriv(deriv)
    line = tree.to_string()
    if hparams.merge_bpe:
      line = line.replace(' ', '')
      line = line.replace('▁', ' ').strip()
    out_file.write(line + '\n')
    out_file.flush()
    out_parse_file.write(tree.to_parse_string() + '\n')
    out_parse_file.flush()
  else:
    h_best_words = map(lambda wi: data.target_index_to_word[wi],
                     filter(lambda wi: wi not in hparams.filtered_tokens, h))
    if hparams.merge_bpe:
      line = ''.join(h_best_words)
      line = line.replace('▁', ' ')
    else:
      line = ' '.join(h_best_words)
    line = line.strip()
    out_file.write(line + '\n')
    out_file.flush()
print("Translated {0} sentences".format(num_sentences))
sys.stdout.flush()

out_file.close()
if args.trdec:
  out_parse_file.close()
