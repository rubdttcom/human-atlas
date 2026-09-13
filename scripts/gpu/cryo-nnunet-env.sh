# Shared environment for the cryosection pilot nnU-Net runs on rub-pc.
# The RTX 3080 is pinned by UUID: the GT 1030 in this box is sm_61 and this torch build does not support it.
export CUDA_VISIBLE_DEVICES=GPU-c6a8fe2b-851a-a14e-3dff-75aab4818c73
export VHF=/media/rub/Backups/VHF
export nnUNet_raw=$VHF/nnunet/raw
export nnUNet_preprocessed=$VHF/nnunet/preprocessed
export nnUNet_results=$VHF/nnunet/results
export PY=$VHF/env-nnunet/bin
export PYTHONHASHSEED=12345
export nnUNet_n_proc_DA=8
