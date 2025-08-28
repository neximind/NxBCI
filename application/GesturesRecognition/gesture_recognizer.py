import os
import logging
import time
import pywt
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from sklearn.utils import shuffle
from datetime import datetime
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split


logger = logging.getLogger()

class CNNModel(nn.Module):
    def __init__(self, n_channels, window_size, n_classes, n_features): 
        super(CNNModel, self).__init__()
        
        self.conv_block1 = nn.Sequential(
            nn.Conv2d(in_channels=1, out_channels=32, kernel_size=(3, 10), padding=(1, 5)),
            nn.ReLU(),
            nn.BatchNorm2d(32),
            nn.MaxPool2d(kernel_size=(1, 2))
        )

        self.conv_block2 = nn.Sequential(
            nn.Conv2d(in_channels=32, out_channels=64, kernel_size=(3, 10), padding=(1, 5)),
            nn.ReLU(),
            nn.BatchNorm2d(64),
            nn.MaxPool2d(kernel_size=(1, 2))
        )

        h_out = n_channels
        w_out = window_size // 2 // 2
        flattened_size = 64 * h_out * w_out
        self.cnn_output_layer = nn.Sequential(
            nn.Flatten(),
            nn.Linear(flattened_size, 128),
            nn.ReLU(),
            nn.BatchNorm1d(128)
        )

        self.feature_processor = nn.Sequential(
            nn.Linear(n_features, 64),
            nn.ReLU(),
            nn.BatchNorm1d(64)
        )
        
        self.classifier = nn.Sequential(
            nn.Linear(128 + 64, 128),
            nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(128, n_classes)
        )

    def forward(self, x_raw, x_features):
       
        cnn_out = self.conv_block1(x_raw)
        cnn_out = self.conv_block2(cnn_out)
        cnn_out = self.cnn_output_layer(cnn_out)
        
        feature_out = self.feature_processor(x_features)
        combined = torch.cat((cnn_out, feature_out), dim=1)
        logits = self.classifier(combined)
        return logits


class GestureRecognizer:
    
    def __init__(self, gestures, channels=8, window_size=1000, stride=250, random_state=42):
        self.gestureNames = gestures
        self.n_channels = channels
        self.window_size = window_size
        self.stride = stride
        self.random_state = random_state
        self.n_classes = len(gestures)
        
        self.device = self.get_device()
        logger.info(f"Using device: {self.device}")

        self.n_features = self.n_channels * (4 + 6) # 4 (RMS, MAV, ZC, SSC) + 6 (WT)
        logger.info(f"Each window will have {self.n_features} features extracted.")

        if self.window_size % self.stride != 0:
            raise ValueError(f"window_size ({self.window_size}) must be perfectly divisible by stride ({self.stride}).")
        
        self.model = CNNModel(self.n_channels, self.window_size, self.n_classes, self.n_features).to(self.device)
        
        self.test_acc = 0.0
        self.rms_threshold = 0.0
        self.gesture_to_label = {name: i for i, name in enumerate(self.gestureNames)}
        self.label_to_gesture = {i: name for i, name in enumerate(self.gestureNames)}
        
        np.random.seed(random_state)
        torch.manual_seed(random_state)

        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(random_state)

    def get_device(self):

        device = torch.device("cpu")

        if torch.cuda.is_available():
            device = torch.device("cuda")
            logger.info(f"Using CUDA: {torch.cuda.get_device_name(0)}")

        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available() and torch.backends.mps.is_built():
            device = torch.device("mps")
            logger.info("Using Apple Silicon MPS")

        else:
            logger.info("Using CPU")
        
        return device

    def calculate_rms_threshold(self, raw_data, percentile=95):
        window_rms_values = []
        num_windows = (raw_data.shape[1] - self.window_size) // self.stride + 1
        
        for i in range(num_windows):
            start = i * self.stride
            window = raw_data[:, start : start + self.window_size]

            if window.shape[1] == self.window_size:
                rms = np.mean(np.sqrt(np.mean(window**2, axis=1)))
                window_rms_values.append(rms)
                
        if not window_rms_values:
            logger.warning("Cannot compute RMS threshold: No valid windows found.")
            return
            
        self.rms_threshold = np.percentile(window_rms_values, percentile)
        logger.info(f"RMS threshold set to {self.rms_threshold:.4f} (percentile: {percentile})")


    def extract_emg_features(self,window):
        features = []
        for channel_data in window:
            # 1.RMS
            rms = np.sqrt(np.mean(channel_data**2))
            features.append(rms)

            # 2.MAV
            mav = np.mean(np.abs(channel_data))
            features.append(mav)

            # 3.ZC
            zc = ((channel_data[:-1] * channel_data[1:]) < 0).sum()
            features.append(zc)

            # 4.SSC
            ssc = ((channel_data[1:-1] - channel_data[:-2]) * (channel_data[1:-1] - channel_data[2:]) > 0).sum()
            features.append(ssc)
            
            # 5.WT
            coeffs = pywt.wavedec(channel_data, 'db4', level=5)
            for coeff in coeffs:
                features.append(np.sum(coeff**2))

        return np.array(features)


    def _load_data_from_files(self, data_dir):
        raw_data_dict = {}

        for gesture in self.gestureNames:
            filename = f"{gesture}_data.npz"
            filepath = os.path.join(data_dir, filename)

            if not os.path.exists(filepath):
                logger.warning(f"file '{filename}' not found in '{data_dir}', skipping.")
                continue
            
            with np.load(filepath) as data:
                raw_data_dict[gesture] = data[data.files[0]][0:self.n_channels, :]

        if not raw_data_dict:
            raise FileNotFoundError(f"Invalid data directory or no valid gesture files found in '{data_dir}'.")
        
        return raw_data_dict

    def _process_raw_data_to_windows(self, raw_data_dict):
        all_windows, all_features, all_labels = [], [], []
        
        for gesture, raw_data in raw_data_dict.items():
            if gesture not in self.gesture_to_label:
                logger.warning(f"The gesture '{gesture}' is not recognized, skipping.")
                continue

            label = self.gesture_to_label[gesture]
            logger.info(f"Processing gesture '{gesture}' with label {label}...")
            
            num_windows = (raw_data.shape[1] - self.window_size) // self.stride + 1

            for i in range(num_windows):
                start = i * self.stride
                window = raw_data[:, start : start + self.window_size]

                if window.shape[1] == self.window_size:
                    all_windows.append(window)
                    features = self.extract_emg_features(window)
                    all_features.append(features)
                    all_labels.append(label)

            logger.info(f" Generated {num_windows} windows for gesture '{gesture}'.")

        if not all_windows:
            raise ValueError("No valid data windows were generated from the provided raw data.")
        
        X_raw_np = np.array(all_windows).reshape(-1, 1, self.n_channels, self.window_size)
        X_features_np = np.array(all_features)
        y_np = np.array(all_labels)
        
        X_raw_shuffled, X_features_shuffled, y_shuffled = shuffle(
            X_raw_np, X_features_np, y_np, random_state=self.random_state
        )
        
        X_raw_tensor = torch.tensor(X_raw_shuffled, dtype=torch.float32)
        X_features_tensor = torch.tensor(X_features_shuffled, dtype=torch.float32)
        y_tensor = torch.tensor(y_shuffled, dtype=torch.long)
        
        return X_raw_tensor, X_features_tensor, y_tensor

    def _add_gaussian_noise(self, data_tensor, noise_level=0.02):
        noise = torch.randn_like(data_tensor) * noise_level
        return data_tensor + noise

    def train(self, data_dir=None, data_dict=None, test_size=0.2, augment=True, epochs=40, batch_size=64, learning_rate=1e-3,progress_callback=None):
        start_time = time.perf_counter()
        
        if data_dict:
            logger.info("===== [Train Model] Load data from the provided data dictionary for training. =====")
            raw_data = data_dict

        elif data_dir:
            logger.info(f"===== [Train Model] Load data from the directory '{data_dir}' for training. =====")
            raw_data = self._load_data_from_files(data_dir)

        else:
            raise ValueError("Either data_dir or data_dict must be provided for training.")

        logger.info("===== [Train Model] Data processing and feature extraction stage =====")

        X_raw, X_features, y_data = self._process_raw_data_to_windows(raw_data)
        
        logger.info("===== [Train Model] Dataset partitioning phase =====")

        indices = np.arange(X_raw.shape[0])
        train_indices, test_indices = train_test_split(
            indices, test_size=test_size, stratify=y_data.numpy(), random_state=self.random_state
        )
        
        X_raw_train, X_raw_test = X_raw[train_indices], X_raw[test_indices]
        X_feat_train, X_feat_test = X_features[train_indices], X_features[test_indices]
        y_train, y_test = y_data[train_indices], y_data[test_indices]
        
        if augment:
            logger.info("===== [Train Model] Data augmentation phase (only for the original signal) =====")
            logger.info(f"Raw training set size before augmentation: {X_raw_train.shape[0]}")
            X_raw_train_augmented = self._add_gaussian_noise(X_raw_train)
            
            X_raw_train = torch.cat([X_raw_train, X_raw_train_augmented])
            X_feat_train = torch.cat([X_feat_train, X_feat_train])
            y_train = torch.cat([y_train, y_train])
            
            perm = torch.randperm(X_raw_train.size(0))
            X_raw_train, X_feat_train, y_train = X_raw_train[perm], X_feat_train[perm], y_train[perm]
            
            logger.info(f"Raw training set size after augmentation: {X_raw_train.shape[0]}")
        
        train_dataset = TensorDataset(X_raw_train, X_feat_train, y_train)
        test_dataset = TensorDataset(X_raw_test, X_feat_test, y_test)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)
        
        logger.info("===== [Train Model] Model training stage =====")
        logger.info(self.model)
        
        criterion = nn.CrossEntropyLoss()
        optimizer = optim.Adam(self.model.parameters(), lr=learning_rate)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'max', factor=0.5, patience=3)
        
        best_val_loss = float('inf')
        patience_counter = 0
        patience = 8
        best_model_state = None

        for epoch in range(epochs):
            if progress_callback: progress_callback(epoch + 1, epochs)
            self.model.train()
            total_train_loss = 0
            
            for X_raw_batch, X_feat_batch, y_batch in train_loader:
                X_raw_batch, X_feat_batch, y_batch = X_raw_batch.to(self.device), X_feat_batch.to(self.device), y_batch.to(self.device)
                
                optimizer.zero_grad()
                outputs = self.model(X_raw_batch, X_feat_batch)
                loss = criterion(outputs, y_batch)
                loss.backward()
                optimizer.step()
                total_train_loss += loss.item()

            self.model.eval()
            total_val_loss = 0
            correct_val = 0
            total_val = 0

            with torch.no_grad():
                for X_raw_batch, X_feat_batch, y_batch in test_loader:
                    X_raw_batch, X_feat_batch, y_batch = X_raw_batch.to(self.device), X_feat_batch.to(self.device), y_batch.to(self.device)
                    outputs = self.model(X_raw_batch, X_feat_batch)
                    loss = criterion(outputs, y_batch)
                    total_val_loss += loss.item()
                    
                    _, predicted = torch.max(outputs.data, 1)
                    total_val += y_batch.size(0)
                    correct_val += (predicted == y_batch).sum().item()
            
            avg_train_loss = total_train_loss / len(train_loader)
            avg_val_loss = total_val_loss / len(test_loader)
            val_accuracy = correct_val / total_val

            logger.info(f'Epoch [{epoch+1}/{epochs}], Train Loss: {avg_train_loss:.4f}, Val Loss: {avg_val_loss:.4f}, Val Acc: {val_accuracy:.4f}')
            scheduler.step(val_accuracy)

            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                patience_counter = 0
                best_model_state = self.model.state_dict()
                self.test_acc = val_accuracy
            else:
                patience_counter += 1
            
            if patience_counter >= patience:
                logger.info("Early stopping triggered!")
                break
        
        if best_model_state:
            self.model.load_state_dict(best_model_state)
            
        logger.info("===== [Train Model] Model evaluation completed =====")

        logger.info(f"Best test set loss (Loss): {best_val_loss:.4f}")
        logger.info(f"Best test set accuracy (Accuracy): {self.test_acc:.4f}")

        end_time = time.perf_counter()
        logger.info(f"Total training time: {(end_time - start_time):.2f} seconds")

        self.save_model()

    def predict(self, raw_data_window):
        start_time = time.perf_counter()
        
        if not hasattr(self.model, 'conv_block1'):
             logger.error("No trained model available for prediction.")
             return "None"
             
        if raw_data_window is None:
            logger.error("No input data provided for prediction.")
            return "None"

        try:

            input_data = np.array(raw_data_window)

        except Exception as e:
            logger.error(f"Error converting input data to numpy array: {e}")
            return "None"

        if input_data.shape != (self.n_channels, self.window_size):
            logger.error(f"Input data shape {input_data.shape} does not match expected shape ({self.n_channels}, {self.window_size}).")
            return "None"
        
        current_rms = np.mean(np.sqrt(np.mean(input_data**2, axis=1)))
        if self.rms_threshold > 0 and current_rms < self.rms_threshold:
            logger.info(f"Input RMS {current_rms:.4f} below threshold {self.rms_threshold:.4f}, returning None.")
            return "None"
        
        self.model.eval()
        with torch.no_grad():
        
            input_raw_tensor = torch.tensor(input_data, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
            input_raw_tensor = input_raw_tensor.to(self.device)
            
            input_features = self.extract_emg_features(input_data)
            input_feat_tensor = torch.tensor(input_features, dtype=torch.float32).unsqueeze(0)
            input_feat_tensor = input_feat_tensor.to(self.device)

            outputs = self.model(input_raw_tensor, input_feat_tensor)
            probabilities = torch.softmax(outputs, dim=1)
            
            predicted_prob, predicted_label_idx = torch.max(probabilities, 1)
            
            probs_list = probabilities.cpu().numpy().flatten()
            for i, prob in enumerate(probs_list):
                 logger.info(f"Gesture: {self.label_to_gesture[i]}, Probability: {prob:.4f}")

            end_time = time.perf_counter()
            logger.info(f"Prediction time: {(end_time - start_time)*1000:.2f} ms")

            if predicted_prob.item() < 0.9:
                logger.info(f"Predicted probability {predicted_prob.item():.4f} below confidence threshold, returning None.")
                return "None"

            return self.label_to_gesture[predicted_label_idx.item()]


    def save_model(self, model_dir="models"):

        if not hasattr(self.model, 'conv_block1'):
            logger.error("No trained model available to save.")
            return
            
        if not os.path.exists(model_dir):
            os.makedirs(model_dir)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gestures_recognition_{self.test_acc:.4f}_{timestamp}.pth"
        path = os.path.join(model_dir, filename)
        
        save_dict = {
            'model_state_dict': self.model.state_dict(),
            'gestures': self.gestureNames,
            'n_channels': self.n_channels,
            'window_size': self.window_size,
            'stride': self.stride,
            'test_acc': self.test_acc,
            'rms_threshold': self.rms_threshold,
            'random_state': self.random_state,
            'n_features': self.n_features
        }
        torch.save(save_dict, path)
        logger.info(f"Model saved to {path}")

    def load_model(self, path):

        if not os.path.exists(path):
            logger.error(f"Model file '{path}' does not exist.")
            return
            
        checkpoint = torch.load(path, map_location=self.device)
        
        self.gestureNames = checkpoint['gestures']
        self.n_channels = checkpoint['n_channels']
        self.window_size = checkpoint['window_size']
        self.stride = checkpoint['stride']
        self.test_acc = checkpoint['test_acc']
        self.rms_threshold = checkpoint['rms_threshold']
        self.random_state = checkpoint['random_state']
        self.n_features = checkpoint.get('n_features', self.n_channels * 10) 
        self.n_classes = len(self.gestureNames)
        self.gesture_to_label = {name: i for i, name in enumerate(self.gestureNames)}
        self.label_to_gesture = {i: name for i, name in enumerate(self.gestureNames)}

        self.model = CNNModel(self.n_channels, self.window_size, self.n_classes, self.n_features).to(self.device)
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.model.eval()
        
        logger.info(f"Model loaded from {path} with accuracy {self.test_acc:.4f}")

"""
#Example usage:

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
gestures_i = ["fist", "openHand", "left", "right","yes","rest"]
model = GestureRecognizer(gestures=gestures_i,window_size=100,stride=50)
model._load_data_from_files(data_dir='data')
model.train(data_dir='data')
"""