# Embedding Backup Model

This folder is a backup only. It is not imported by `06_real_time_camera.py`, and it does not change the current live camera behavior.

## Purpose

The current live system uses LBPH texture features. This backup builds a more face-specific recognizer using InsightFace embeddings plus a calibrated classifier and prototype checks. It should be less sensitive to hair, background texture, and lighting than LBPH.

## Train

Run from the project root with the same Python interpreter that can run the current camera script:

```bash
python backup_models/embedding_backup/train_embedding_backup_model.py
```

Outputs go to:

```text
backup_models/embedding_backup/artifacts/
```

Embedding extraction is cached under:

```text
backup_models/embedding_backup/artifacts/cache/
```

If the training is interrupted, run the same command again. Already extracted images will be reused from cache.

Expected artifacts:

```text
embedding_backup_model.pkl
backup_model_report.json
```

## Test Loading

After training:

```bash
python backup_models/embedding_backup/backup_embedding_inference.py --image data_split/test/Ainour/<some_image>.jpg
```

## Important

This model is not active. To use it later, we would explicitly wire `BackupEmbeddingRecognizer` into the live camera script. Until then, your current pipeline remains unchanged.
