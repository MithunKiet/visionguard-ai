# Local PPE webcam trial on Windows

Your submitted camera report establishes a 30-second laptop capture at 1280×720, about 29.95 decoded FPS, 899 frames and no read failures. It does not establish detection accuracy. This next step runs an actual public PPE model locally and shows its predictions.

## Run

1. Download/extract the latest `feat/real-camera-validation` branch, or pull it in your existing checkout. 64-bit Python 3.11 for Windows x64 and the Python launcher are required, as with the camera check.
2. Close other camera applications. Double-click **`test-ppe-windows.cmd`** at the project root. It installs CPU inference dependencies in `.venv-webcam` and downloads a roughly 43 MiB model from GitHub. Each download and every model load verifies the pinned SHA-256. Internet is used for setup; webcam frames are never uploaded.
3. Let the preview run for 60 seconds, or press Q/Esc to finish. Start alone, with good lighting and head/torso visible. If available, try a real safety helmet and high-visibility vest, then compare predictions with and without them in a safe indoor setting. A cap or ordinary bright shirt is not a substitute for labeled PPE ground truth. Do not create hazardous scenarios.
4. Share the generated `validation-results/ppe-trial-*.json` report and describe obvious correct/missed/incorrect predictions. The report contains counts and timings, not images or audio. No footage is recorded and no operational alerts are sent.

Camera troubleshooting is the same as the [webcam check](WINDOWS_WEBCAM.md). Try `test-ppe-windows.cmd 0 msmf` for Windows Media Foundation or `test-ppe-windows.cmd 1` for a second camera. CPU inference will usually be slower than camera capture. A background reader keeps only the latest frame so model processing does not intentionally queue a growing video backlog. A parent-process deadline bounds a hung native driver/inference call.

## Model identity and limitations

Source: [M0-AbdElwahab/safety-gear-detector](https://github.com/M0-AbdElwahab/safety-gear-detector/tree/0d9abf9e606e383e932ecb68723b520b4c4b959d), `models/best.onnx`, revision `0d9abf9e606e383e932ecb68723b520b4c4b959d`.

SHA-256: `f7abd19f20a694c6422e7bb9fc647202e0c1cd5c78a3a28f123caeaa87d37098`.

The model is an exported YOLOv8s detector with six classes: `boots`, `helmet`, `nohelmet`, `novest`, `person`, `vest`. The runner verifies its fixed 640×640 input, output shape and class metadata. Inference uses local ONNX Runtime CPU, RGB letterboxing and class-aware non-maximum suppression. Only explicit predicted `nohelmet`/`novest` boxes are highlighted as possible violations. An absent helmet/vest box is **not** converted into a violation or a compliance judgment. Gloves, mask violations, employee identity and violence detection are not supported by this trial.

This is a separate experimental runner, not a replacement for the production detector's nine-class checkpoint. It does not use the production CLAHE/temporal-voting pipeline and does not modify factory configuration, alerts or model deployment. Do not put this ONNX file in `YOLO_MODEL_PATH` expecting the production worker to accept it.

The publisher documents small evaluation sets, overlap between original dataset splits and missed violations, including a missed helmet violation in its demo photo. Its reported metrics do not transfer to your webcam or factory. No claim of accuracy, unique-person counts or safe/compliant status follows from the preview. Repeated frame detections are counted repeatedly in the report; inference time is not capture-to-alert latency. Reports always retain `accuracy_validated=false` and `production_approved=false`.

The model metadata identifies **AGPL-3.0** and links to [Ultralytics licensing](https://ultralytics.com/license). The publisher attributes training data to [PPE_master v1 by harshaJSN](https://universe.roboflow.com/harshajsn/ppe_master), **CC BY 4.0**, and notes possible stock-photo provenance issues in that dataset. We download the original model unchanged and do not redistribute dataset images. Preserve attribution and assess model/dataset license obligations before commercial integration. This trial does not establish a commercial license or promote the model to production.

After the trial, use [PPE_ACCURACY_EVALUATION.md](PPE_ACCURACY_EVALUATION.md) to label independent examples and measure per-class errors with the six-class ONNX evaluator. [REAL_CAMERA_VALIDATION.md](REAL_CAMERA_VALIDATION.md) describes the broader study; its production evaluator targets the separate nine-class model. Keep their class mappings and datasets separate.
