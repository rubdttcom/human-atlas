#!/usr/bin/env python
"""Entry point for the cryosection pilot nnU-Net runs.

This file exists so that __main__ has a real path on disk. nnU-Net builds its
validation export pool with multiprocessing in 'spawn' mode, and a spawned child
re-imports __main__ from that path. The launchers used to feed the run through
stdin ("$PY/python" - 502 <<'PY'), so every child died on startup with
FileNotFoundError: '/media/rub/Backups/VHF/<stdin>'. The parent then waited for
results that never arrived. Training survived because the dataloaders fork; the
post-training validation did not. That hung the rgb-only run on 2026-09-14 and
the rgb-plus-ct-prior run on 2026-09-15.
"""
import argparse
import random

import numpy as np
import torch

from nnunetv2.run.run_training import run_training

SEED = 12345


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="nnU-Net dataset name or id")
    parser.add_argument("--mode", choices=("train", "resume", "validate"), default="train",
                        help="train from scratch, continue from checkpoint_latest, "
                             "or only run the validation of checkpoint_final")
    args = parser.parse_args()

    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)

    # run_training asserts that these two are never both true.
    run_training(args.dataset, "2d", 0, "nnUNetTrainer", "nnUNetPlans",
                 continue_training=args.mode == "resume",
                 only_run_validation=args.mode == "validate",
                 device=torch.device("cuda"))


if __name__ == "__main__":
    main()
