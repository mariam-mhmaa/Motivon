# Face Recognition System - Setup & Usage Instructions

## Overview
This is a complete face recognition system that identifies one of 4 people (Ainour, Mariam, Nour, Zeina) or marks them as "UNKNOWN". The system uses state-of-the-art face embedding extraction with InsightFace and SVM classification.

## System Architecture

```
Raw Images → Preprocessing → Train/Val/Test Split → Model Training
                ↓                                          ↓
        Face Detection                              SVM Classifier
        Data Cleaning                            (on embeddings)
        Face Extraction                               ↓
                                              Real-time Testing
```

## Prerequisites

### System Requirements
- Python 3.8 or higher
- CUDA 11.x or higher (optional, for GPU acceleration)
- Webcam (for real-time testing)
- At least 4GB RAM
- Storage: ~2GB for model and data

### Installation Steps

1. **Clone/Download the project**
   ```bash
   cd "Vision again"
   ```

2. **Create a virtual environment (recommended)**
   ```bash
   python -m venv venv
   
   # On Windows
   venv\Scripts\activate
   
   # On Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

   The requirements include:
   - `opencv-python` - Computer vision library
   - `insightface` - Face detection and embedding extraction
   - `onnxruntime` - Model inference engine
   - `scikit-learn` - Machine learning classifier
   - `numpy` - Numerical computations
   - `matplotlib` - Visualization
   - `tqdm` - Progress bars

4. **Verify installation**
   ```bash
   python -c "import cv2; import insightface; print('✓ Installation successful')"
   ```

## Step-by-Step Usage

### Option 1: Run Complete Pipeline (Recommended for First Time)

```bash
python run_pipeline.py
```

This will execute all steps automatically:
1. Data exploration and statistics
2. Image preprocessing and face detection
3. Train/test/validation split
4. Model training
5. Model testing and evaluation

### Option 2: Run Individual Steps

**Step 1: Explore Dataset**
```bash
python 01_data_exploration.py
```
Outputs: `dataset_stats.json` with dataset statistics

**Step 2: Preprocess Images**
```bash
python 02_data_preprocessing.py
```
Outputs:
- `processed_images/` - Cleaned face images
- `invalid_images/` - Images with issues (multiple faces, no faces, corrupted)

**Step 3: Split Dataset**
```bash
python 03_train_test_split.py
```
Outputs: `data_split/` with train (70%), validation (15%), test (15%) sets

**Step 4: Train Model**
```bash
python 04_train_model.py
```
Outputs:
- `models/classifier.pkl` - Trained SVM classifier
- `models/label_encoder.pkl` - Label encoder
- `models/class_labels.pkl` - Class names

**Step 5: Test Model**
```bash
python 05_test_model.py
```
Outputs:
- Console metrics (accuracy, precision, recall, F1)
- `confusion_matrix_test.png` - Visualization

**Step 6: Real-Time Camera Testing**
```bash
python 06_real_time_camera.py
```
Controls:
- `SPACE` - Toggle prediction smoothing
- `C` - Capture screenshot
- `Q` - Quit

## Output Files

### Directory Structure After Execution
```
Vision again/
├── raw_images/                 # Original images (input)
│   ├── Ainour/
│   ├── Mariam/
│   ├── Nour/
│   └── Zeina/
├── processed_images/           # Cleaned face crops
│   ├── Ainour/
│   ├── Mariam/
│   ├── Nour/
│   └── Zeina/
├── invalid_images/             # Images with issues
│   ├── Ainour/
│   ├── Mariam/
│   ├── Nour/
│   └── Zeina/
├── data_split/                 # Train/Val/Test split
│   ├── train/
│   ├── val/
│   └── test/
├── models/                      # Trained models
│   ├── classifier.pkl
│   ├── label_encoder.pkl
│   └── class_labels.pkl
├── dataset_stats.json          # Dataset statistics
└── confusion_matrix_test.png   # Test metrics visualization
```

## Model Details

### Face Embedding Extraction: InsightFace
- **Model**: buffalo_l (ResNet100 backbone)
- **Input Size**: 640×640 (detection), 224×224 (recognition)
- **Embedding Dimension**: 512-d vectors
- **Pre-trained**: Yes (no fine-tuning needed)

### Classifier: Support Vector Machine (SVM)
- **Kernel**: RBF (Radial Basis Function)
- **Training Data**: Face embeddings from train set
- **Output**: Probability scores for each person
- **Confidence Threshold**: 0.5 (configurable)

### Decision Logic
```
If max_probability >= 0.5:
    Predict: Person name
Else:
    Predict: UNKNOWN
```

## Features

### 1. Data Preprocessing
- Automatic face detection using InsightFace
- Removal of:
  - Images with no detected faces
  - Images with multiple faces
  - Corrupted/invalid images
- Face cropping with 20-pixel padding
- Standardized size (224×224)

### 2. Quality Checks
- Validates all images in preprocessing
- Skips corrupted files automatically
- Generates detailed statistics and logs
- Identifies invalid images for manual review

### 3. Training
- Automatic train/val/test split (70%/15%/15%)
- Stratified splitting (preserves class distribution)
- Embedding extraction from all train images
- SVM training on embeddings
- Validation monitoring

### 4. Evaluation
- Per-person accuracy metrics
- Overall accuracy, precision, recall, F1-score
- Confusion matrix visualization
- Confidence distribution analysis

### 5. Real-Time Recognition
- Single most prominent face detection
- Temporal smoothing (optional)
- Adjustable confidence threshold
- Visual feedback (color-coded bounding boxes)
- Screenshot capture capability

## Performance Tips

### Speed Optimization
- **GPU**: Ensure ONNX Runtime uses GPU (check during first run)
- **Resolution**: Lower camera resolution for faster processing
- **Smoothing**: Enable for more stable predictions

### Accuracy Improvement
1. **More Training Data**: Add more images per person
2. **Lighting**: Vary lighting conditions during data collection
3. **Angles**: Capture faces from different angles
4. **Expressions**: Include different facial expressions
5. **Lower Threshold**: Reduce confidence threshold for more lenient recognition (0.3-0.4)

## Troubleshooting

### Issue: "No GPU found"
- Install CUDA and cuDNN (optional, CPU works too)
- Or use CPU (slower but works)

### Issue: "No faces detected"
- Check image quality and lighting
- Ensure faces are clearly visible
- Remove corrupted images

### Issue: "Multiple faces in image"
- Ensure only one face per image during data collection
- Invalid images are automatically moved to `invalid_images/`

### Issue: Low accuracy
- Check data quality (run `01_data_exploration.py`)
- Ensure each person has enough training images (ideally 50+)
- Verify preprocessing (check `processed_images/`)
- Adjust confidence threshold lower if needed

### Issue: Camera not working
- Check if webcam is recognized: `python -c "import cv2; print(cv2.VideoCapture(0).isOpened())"`
- Try camera_id=1 instead of 0
- Check webcam permissions

## System Performance Expectations

### Model Inference Time
- **Per Frame**: ~50-100ms (GPU), ~200-300ms (CPU)
- **FPS**: 10-20 FPS (GPU), 3-5 FPS (CPU)

### Accuracy (Expected)
- **Known Persons**: 85-95% (depends on image quality)
- **Unknown Detection**: 80-90% (depends on confidence threshold)

## Advanced Configuration

### Change Confidence Threshold
In `06_real_time_camera.py`:
```python
system = FaceRecognitionSystem(confidence_threshold=0.4)  # Default: 0.5
```
- Lower threshold = More unknown detections
- Higher threshold = More person recognition

### Change Train/Val/Test Split
In `03_train_test_split.py`:
```python
stats = create_train_val_test_split(
    train_ratio=0.70,  # 70% training
    val_ratio=0.15,    # 15% validation
    test_ratio=0.15    # 15% testing
)
```

### Use Different Camera
In `06_real_time_camera.py`:
```python
system.run_camera(camera_id=0)  # 0 = default, 1 = external, etc.
```

## References

- **InsightFace**: https://github.com/deepinsight/insightface
- **OpenCV**: https://opencv.org/
- **Scikit-learn**: https://scikit-learn.org/

## Support

If you encounter issues:
1. Check the console output for error messages
2. Verify all dependencies are installed
3. Ensure dataset structure is correct
4. Check `dataset_stats.json` for data quality issues
5. Review invalid images in `invalid_images/` folder

---

**Created**: April 2026
**System**: Face Recognition with InsightFace + SVM
