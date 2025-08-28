import logging
import time
import threading
import os
import multiprocessing
import matplotlib.pyplot as plt
import numpy as np
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import ttk, font
from collections import deque
from itertools import islice
from TCP_Receiver import TCP_Receiver
from gesture_recognizer import GestureRecognizer

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- CONFIG and STYLE ---
CONFIG = {
    "data_channels": 8,  # Define the number of data channels to use
    "sample_rate": 500,
    "duration": 4,  # seconds
    "window_time":0.2,#seconds range:200ms-500ms
    "stride_ratio":0.5,# range:0.5-1.0 window_time
    "epochs": 50,
    "batch_size": 64,
    "learning_rate": 1e-3,
    "gestures": {
        "fist": "Make a Fist",
        "left": "Wrist to Left",
        "right": "Wrist to Right",
        "openHand": "Fingers Apart",
        "yes": "Scissorhands/Victory",
        "None": "Rest"
    },
    "images_path": {
        "fist": "images/fist.png",
        "left": "images/left.png",
        "right": "images/right.png",
        "openHand": "images/open_hand.png",
        "yes": "images/yes.png",
        "logo": "images/emg_logo.jpg",
        "relax": "images/relax.png",
        "None": "images/relax.png"
    },
    "collection": {
        "repeats_per_gesture": 5,
        "collect_time": 4,
        "rest_time": 3,
    },
    "calibration": {
        "duration": 12,
        "instruction": "Calibrating, please relax your arms completely and keep still...",
    },
    "save_dir": "data"
}

STYLE = {
    "font_title": ("Arial", 28, "bold"),
    "font_large": ("Arial", 24),
    "font_normal": ("Arial", 16),
    "font_small": ("Arial", 12),
    "color_bg": "#f0f0f0",
    "color_primary": "#007bff",
    "color_success": "#28a745",
    "color_danger": "#dc3545",
    "color_text": "#333333"
}

os.makedirs(CONFIG["save_dir"], exist_ok=True)


# --- HELPER FUNCTIONS ---
def get_latest_from_queue(q):
    """
    Empties a queue and returns only the last item.
    This is crucial for real-time plots to avoid lag.
    """
    data = None
    while not q.empty():
        try:
            data = q.get_nowait()
        except multiprocessing.queues.Empty:
            continue
    return data

def process_and_validate_data(raw_data, expected_channels):
    """
    Validates the number of channels from the raw data.
    - Truncates data if there are too many channels.
    - Raises ValueError if there are too few channels.
    """
    if not raw_data or not raw_data[0]:
        return None  # Handle cases with no data
    
    actual_channels = len(raw_data)
    
    if actual_channels < expected_channels:
        error_msg = f"Insufficient data channels. Expected {expected_channels}, but received {actual_channels}."
        logging.error(error_msg)
        raise ValueError(error_msg)
    
    if actual_channels > expected_channels:
        logging.warning(f"Received {actual_channels} channels, but only the first {expected_channels} will be used as configured.")
        return np.array(raw_data[:expected_channels])
    
    return np.array(raw_data) # Perfect match

def run_plot_process(data_queue, num_channels):
    """
    Receives data and plots it using the high-performance blitting technique.
    This version uses a blocking queue.get() to eliminate flickering and reduce CPU usage.
    """
    MAX_POINTS = CONFIG['sample_rate']*CONFIG["duration"]
    OFFSET = 200

    try:
        fig, ax = plt.subplots(figsize=(15, 9))
        
        lines = [ax.plot([], [], lw=1, animated=True)[0] for _ in range(num_channels)]

        ax.set_title(f"{num_channels}-Channel Real-Time Data Plot")
        ax.set_xlabel("Time Points")
        ax.set_ylabel("Voltage (Channels separated by offset)")
        ax.set_xlim(0, MAX_POINTS)
        ax.set_ylim(-OFFSET, num_channels * OFFSET)
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.set_yticks([])
        fig.tight_layout()

        x_data_full = np.arange(MAX_POINTS)
        
        plt.show(block=False)
        plt.pause(0.1) # A single pause here is fine to ensure the window is drawn initially
        
        bg = fig.canvas.copy_from_bbox(fig.bbox)
        
        for line in lines:
            ax.draw_artist(line)

        print("Plotting window is active. Close this window to stop plotting.")

        while plt.fignum_exists(fig.number):
            latest_data = None
            try:
                # --- KEY CHANGE 1: Block until data is available ---
                # This is the efficient way to wait. It uses almost no CPU and avoids plt.pause().
                # A timeout is added to prevent it from blocking forever if the main app closes unexpectedly.
                latest_data = data_queue.get(timeout=1)

                # --- KEY CHANGE 2: Drain the queue to get the most recent data ---
                # This ensures the plot doesn't lag if data is produced faster than it's plotted.
                while not data_queue.empty():
                    try:
                        latest_data = data_queue.get_nowait()
                    except multiprocessing.queues.Empty:
                        break
            
            except multiprocessing.queues.Empty:
                # If the timeout is reached and there's no data, just continue the loop.
                # This keeps the plot window responsive to being closed.
                continue

            # --- Blitting animation loop (no changes here) ---
            fig.canvas.restore_region(bg)
            
            # Ensure we don't plot more channels than we have lines for
            for i in range(min(num_channels, len(latest_data))):
                y_points = latest_data[i]
                current_len = len(y_points)
                if current_len > 0:
                    y_data = np.array(y_points) + i * OFFSET
                    lines[i].set_data(x_data_full[:current_len], y_data)
                    ax.draw_artist(lines[i])

            fig.canvas.blit(fig.bbox)
            fig.canvas.flush_events()

    except Exception as e:
        logging.error(f"An error occurred in the plotting process: {e}")
    finally:
        print("Plotting process has ended.")

class EMGApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EMG Gesture Recognition")
        self.geometry("1200x800")
        self.configure(bg=STYLE["color_bg"])

        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(family="Arial", size=12)

        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure("TButton", font=STYLE["font_normal"], padding=10)
        style.configure("TLabel", background=STYLE["color_bg"], foreground=STYLE["color_text"])
        style.configure("TFrame", background=STYLE["color_bg"])
        style.configure("Green.Horizontal.TProgressbar", foreground=STYLE['color_success'], background=STYLE['color_success'])

        self.frames = {}
        self.pred_history = deque(maxlen=10)
        self.plot_queue = multiprocessing.Queue(maxsize=10)
        self.plot_process = None

        container = ttk.Frame(self)
        container.pack(side="top", fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.calibration_data = None
        self.gestureData = {}
        # Configure TCP_Receiver with the number of channels from CONFIG
        self.receiver = TCP_Receiver(channels=CONFIG["data_channels"], sample_rate=CONFIG["sample_rate"], duration=CONFIG["duration"],Ip="192.168.4.1", port=8080)
        self.receiver.start()
        
        gestures_i = list(CONFIG["gestures"].keys())

        windowSize = int(CONFIG["sample_rate"]*CONFIG["window_time"])  # 0.25 second window
        stride = int(windowSize*CONFIG['stride_ratio'])  # 50% overlap
        self.model = GestureRecognizer(gestures=gestures_i, channels=CONFIG["data_channels"],window_size=windowSize, stride=stride)
        self.predict_label = "None"
        self.predict_label_lock = threading.Lock()
  
        self.data_forwarder_thread = threading.Thread(target=self._data_forwarder_task, daemon=True)
        self.data_forwarder_thread.start()

        for F in (MainMenu, GameCollector):
            frame = F(container, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame(MainMenu)
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def show_frame(self, frame_class):
        frame = self.frames[frame_class]
        frame.tkraise()
        if hasattr(frame, "on_show"):
            frame.on_show()
            
    def _data_forwarder_task(self):
        while True:
            if self.plot_process and self.plot_process.is_alive():
                data = self.receiver.get_data()
                try:
                    if self.plot_queue.full():
                        get_latest_from_queue(self.plot_queue)
                    self.plot_queue.put_nowait(data)
                except multiprocessing.queues.Full:
                    pass
            time.sleep(0.02)
            
    def on_closing(self):
        print("Closing the application...")
        if self.plot_process and self.plot_process.is_alive():
            print("Stopping the plot process...")
            self.plot_process.terminate()
            self.plot_process.join()
        self.receiver.stop()
        print("TCP receiver stopped.")
        self.destroy()


class MainMenu(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        control_frame = ttk.Frame(self, padding="20 40")
        control_frame.grid(row=0, column=0, sticky="nsew")
        control_frame.grid_rowconfigure(6, weight=1)

        tk.Label(control_frame, text="Control Panel", font=STYLE["font_large"], fg=STYLE["color_primary"], bg=STYLE["color_bg"]).grid(row=0, column=0, pady=(0, 30), sticky="w")
        
        self.btn_collect = ttk.Button(control_frame, text="Start Data Collection", command=self.start_collecting)
        self.btn_collect.grid(row=1, column=0, pady=10, sticky="ew")

        self.btn_train = ttk.Button(control_frame, text="Train Model", command=self.start_training)
        self.btn_train.grid(row=2, column=0, pady=10, sticky="ew")

        self.btn_show_plot = ttk.Button(control_frame, text="Show Real-time Waveform", command=self.toggle_plot_window)
        self.btn_show_plot.grid(row=3, column=0, pady=10, sticky="ew")
        
        self.status_label = tk.Label(control_frame, text="Status: Standby", font=STYLE["font_normal"], bg=STYLE["color_bg"])
        self.status_label.grid(row=4, column=0, pady=20, sticky="w")
        
        self.train_progress_bar = ttk.Progressbar(control_frame, orient="horizontal", length=400, mode="determinate",style="Green.Horizontal.TProgressbar")
        self.train_progress_bar.grid(row=5, column=0, pady=5, sticky="ew")
        self.train_progress_bar.grid_remove() 

        result_frame = ttk.Frame(self, padding="20 40")
        result_frame.grid(row=0, column=1, sticky="nsew", padx=(10,0))
        result_frame.grid_rowconfigure(2, weight=1)

        tk.Label(result_frame, text="Real-time Prediction", font=STYLE["font_large"], fg=STYLE["color_primary"], bg=STYLE["color_bg"]).grid(row=0, column=0, columnspan=2, pady=(0, 20), sticky="w")

        self.pred_img_label = tk.Label(result_frame, bg=STYLE["color_bg"])
        self.pred_img_label.grid(row=1, column=0, columnspan=2, pady=10)

        self.pred_text_label = tk.Label(result_frame, text="Predicted Gesture: None", font=STYLE["font_large"], bg=STYLE["color_bg"])
        self.pred_text_label.grid(row=2, column=0, columnspan=2, pady=10)

        self.history_label = tk.Label(result_frame, text="Recent Prediction History:", justify=tk.LEFT, font=STYLE["font_small"], bg=STYLE["color_bg"])
        self.history_label.grid(row=3, column=0, sticky="w", pady=10)
        
        self.update_prediction_display()

    def update_train_progress(self, current_epoch, max_epoch):
        if max_epoch > 0:
            progress_percent = (current_epoch / max_epoch) * 100
            self.train_progress_bar['value'] = progress_percent
            self.status_label.config(text=f"Status: Training... Epoch {current_epoch}/{max_epoch}")
            self.update_idletasks()

    def toggle_plot_window(self):
        if self.controller.plot_process and self.controller.plot_process.is_alive():
            print("Requesting termination of the plot process from the GUI...")
            self.controller.plot_process.terminate()
            self.controller.plot_process.join()
            self.controller.plot_process = None
            self.btn_show_plot.config(text="Show Real-time Waveform")
            print("The plot process has been terminated.")
        else:
            print("Starting high-performance plotting process...")
            get_latest_from_queue(self.controller.plot_queue)
            
            # Pass the number of channels from CONFIG to the plotting process
            num_plot_channels = CONFIG["data_channels"]
            p = multiprocessing.Process(target=run_plot_process, args=(self.controller.plot_queue, num_plot_channels))
            p.daemon = True
            p.start()
            self.controller.plot_process = p
            self.btn_show_plot.config(text="Hide Real-time Waveform")

    def start_collecting(self):
        self.controller.show_frame(GameCollector)

    def start_training(self):
        self.status_label.config(text="Status: Training model, please wait...", fg=STYLE["color_primary"])
        self.train_progress_bar.grid()
        self.train_progress_bar['value'] = 0
        self.update_idletasks()
        self.btn_train.config(state="disabled")
        self.btn_collect.config(state="disabled")
        threading.Thread(target=self._train_task, daemon=True).start()

    def _train_task(self):
        try:
            print("Model training starts...")
            if self.controller.calibration_data  is None:
                #self.controller.model.model._load_data_from_files(data_dir='data')
                self.controller.model.train(data_dir='data',progress_callback=self.update_train_progress,epochs=CONFIG["epochs"],batch_size=CONFIG["batch_size"],learning_rate=CONFIG["learning_rate"])
            else:
                self.controller.gestureData["None"] = self.controller.calibration_data
                self.controller.model.train(data_dict=self.controller.gestureData, progress_callback=self.update_train_progress,epochs=CONFIG["epochs"],batch_size=CONFIG["batch_size"],learning_rate=CONFIG["learning_rate"])
            print("Model training completed!")
            self.update_train_progress(1, 1)
            self.status_label.config(text="Status: Training complete! Ready to predict.", fg=STYLE["color_success"])
            time.sleep(2) 
            self.train_progress_bar.grid_remove()

            threading.Thread(target=self._predict_loop, daemon=True).start()
        except Exception as e:
            self.status_label.config(text=f"Status: Training failed: {e}", fg=STYLE["color_danger"])
        finally:
            self.btn_train.config(state="normal")
            self.btn_collect.config(state="normal")

    def _predict_loop(self):
        while True:
            raw_data = self.controller.receiver.get_data()
            
            # Simple check for robustness in the prediction loop
            num_channels = CONFIG["data_channels"]
            if len(raw_data) < num_channels:
                logging.warning(f"Skipping prediction: not enough channels. Got {len(raw_data)}, need {num_channels}.")
                time.sleep(1) # Avoid spamming logs if the issue persists
                continue
            
            # Process only the required number of channels
            end_index = CONFIG["sample_rate"]*CONFIG["duration"]
            windowSize = int(CONFIG["sample_rate"]*CONFIG["window_time"])
            start_index = end_index - windowSize
            data = [list(islice(raw_data[c], start_index, end_index)) for c in range(num_channels)]

            if data and data[0]:
                pred = self.controller.model.predict(data)
                pred = pred[0] if isinstance(pred, list) else pred
                with self.controller.predict_label_lock:
                    self.controller.predict_label = pred
                self.controller.pred_history.append(pred)
            time.sleep(0.001)

    def update_prediction_display(self):
        if self.controller.pred_history:
            last_pred = self.controller.pred_history[-1]
            last_pred_name = CONFIG["gestures"].get(last_pred, "Unknown")
            
            image_key = last_pred if last_pred in CONFIG["images_path"] else "None"
            try:
                if image_key !="None":
                    img = Image.open(CONFIG["images_path"][image_key]).resize((300, 300), Image.Resampling.LANCZOS)
                    self.tk_img = ImageTk.PhotoImage(img)
                    self.pred_img_label.config(image=self.tk_img)
            except FileNotFoundError:
                self.pred_img_label.config(image=None, text=f"Image not found for: {last_pred}")

            self.pred_text_label.config(text=f"Predicted Gesture: {last_pred_name}")
            history_text = "Recent Prediction History:\n" + "\n".join(f"- {CONFIG['gestures'].get(p, 'Unknown')}" for p in reversed(self.controller.pred_history))
            self.history_label.config(text=history_text)
        self.after(50, self.update_prediction_display)


class GameCollector(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=0)
        self.grid_rowconfigure(4, weight=0)
        
        self.image_label = tk.Label(self, bg=STYLE["color_bg"])
        self.image_label.grid(row=0, column=0, pady=20)
        self.prompt_label = tk.Label(self, text="", font=STYLE["font_large"], bg=STYLE["color_bg"])
        self.prompt_label.grid(row=1, column=0, pady=20)
        self.countdown_label = tk.Label(self, text="", font=("Arial", 60, "bold"), bg=STYLE["color_bg"])
        self.countdown_label.grid(row=2, column=0, pady=20)
        self.progress = ttk.Progressbar(self, orient="horizontal", length=500, mode="determinate", style="Green.Horizontal.TProgressbar")
        self.progress.grid(row=3, column=0, pady=20)
        self.btn_back = ttk.Button(self, text="Return to Main Menu", command=self.go_to_main_menu, state="disabled")
        self.btn_back.grid(row=4, column=0, pady=20)
        self.collection_thread = None

    def on_show(self):
        if self.collection_thread is None or not self.collection_thread.is_alive():
            self.btn_back.config(state="disabled")
            self.collection_thread = threading.Thread(target=self._run_collection_flow, daemon=True)
            self.collection_thread.start()
            
    def go_to_main_menu(self):
        self.controller.show_frame(MainMenu)

    def _run_calibration_stage(self):
        try:
            duration = CONFIG["calibration"]["duration"]
            self.progress["value"] = 0
            self.image_label.config(image=None)
            try:
                img = Image.open(CONFIG["images_path"]["relax"]).resize((300, 300), Image.Resampling.LANCZOS)
                self.tk_img_relax = ImageTk.PhotoImage(img) 
                self.image_label.config(image=self.tk_img_relax)
            except FileNotFoundError:
                self.image_label.config(text="Relaxation image missing", font=STYLE["font_normal"])
                
            self.prompt_label.config(text=CONFIG["calibration"]["instruction"], fg=STYLE["color_text"])

            calibration_data_chunks = []
            for i in range(duration, 0, -1):
                self.countdown_label.config(text=str(i), fg=STYLE["color_primary"])
                if i % 4 == 1:
                    try:
                        raw_data = self.controller.receiver.get_data()
                        # Validate the received data
                        processed_data = process_and_validate_data(raw_data, CONFIG["data_channels"])
                        if processed_data is not None:
                            calibration_data_chunks.append(processed_data)
                    except ValueError as e:
                        # Display error to the user and abort
                        self.prompt_label.config(text=str(e), fg=STYLE["color_danger"])
                        time.sleep(3)
                        return False
                time.sleep(1)
            
            self.prompt_label.config(text="Calibrating...", fg=STYLE["color_danger"])
            self.countdown_label.config(text="")
            time.sleep(1.5)
           
            if not calibration_data_chunks:
                logging.error("Calibration failed: No data collected.")
                self.prompt_label.config(text="Calibration failed: Could not collect data.", fg=STYLE["color_danger"])
                time.sleep(1.5)
                return False

            self.controller.calibration_data = np.concatenate(calibration_data_chunks, axis=1)
            #self.controller.model.calculate_rms_threshold(self.controller.calibration_data)
            np.savez(f"./{CONFIG['save_dir']}/rest_data.npz", self.controller.calibration_data)
            logging.info(f"Calibration data collection is complete. Shape: {self.controller.calibration_data.shape}")

            self.prompt_label.config(text="Calibration complete!", fg=STYLE["color_success"])
            time.sleep(1.5)
            return True
        
        except Exception as e:
            logging.error(f"An error occurred during calibration: {e}")
            self.prompt_label.config(text=f"Error during calibration: {e}", fg=STYLE["color_danger"])
            return False

    def _run_collection_flow(self):
        if not self._run_calibration_stage():
            self._update_ui_for_finish(message="Calibration failed. Returning to main menu.")
            return
        
        gestures_to_collect = {k: v for k, v in CONFIG["gestures"].items() if k != "None"}
        repeats = CONFIG["collection"]["repeats_per_gesture"]
        total_steps = len(gestures_to_collect) * repeats
        step_count = 0
        
        self.prompt_label.config(text="Starting data collection...", fg=STYLE["color_primary"])
        time.sleep(2)

        for gesture_key, gesture_name in gestures_to_collect.items():
            gesture_data_chunks = []
            collection_successful = True
            for repeat in range(1, repeats + 1):
                self._update_ui_for_prepare(gesture_key, gesture_name, repeat, repeats)
                self._run_countdown(CONFIG["collection"]["rest_time"], "Resting")
                self._run_countdown(CONFIG["collection"]["collect_time"], "Collecting", color=STYLE["color_danger"])
                
                emg_chunk = self._collect_emg_data(gesture_key, repeat)
                if emg_chunk is not None:
                    gesture_data_chunks.append(emg_chunk)
                else:
                    # An error occurred (e.g., wrong channel count)
                    collection_successful = False
                    break # Stop collecting for this gesture
                
                step_count += 1
                self.progress["value"] = (step_count / total_steps) * 100
            
            if not collection_successful:
                # Abort the entire collection flow if one part fails
                self._update_ui_for_finish(message="Data collection failed. Returning to menu.")
                return

            if gesture_data_chunks:
                full_gesture_data = np.concatenate(gesture_data_chunks, axis=1)
                self.controller.gestureData[gesture_key] = full_gesture_data
                np.savez(f"./{CONFIG['save_dir']}/{gesture_key}_data.npz", full_gesture_data)
                print(f"Gesture '{gesture_name}' data has been merged. Shape: {full_gesture_data.shape}")

        self._update_ui_for_finish()

    def _update_ui_for_prepare(self, gesture_key, gesture_name, repeat, repeats):
        try:
            img = Image.open(CONFIG["images_path"][gesture_key]).resize((300, 300), Image.Resampling.LANCZOS)
            self.tk_img = ImageTk.PhotoImage(img)
            self.image_label.config(image=self.tk_img)
        except FileNotFoundError:
            self.image_label.config(image=None, text=f"Image\n{CONFIG['images_path'][gesture_key]}\nnot found", font=STYLE["font_normal"])
            
        self.prompt_label.config(text=f"Prepare for gesture: {gesture_name} ({repeat}/{repeats})", fg=STYLE["color_text"])
    
    def _run_countdown(self, seconds, title_text, color=STYLE["color_primary"]):
        for i in range(seconds, 0, -1):
            self.countdown_label.config(text=f"{title_text}: {i}", fg=color)
            time.sleep(1)
        self.countdown_label.config(text=f"{title_text}...", fg=color)

    def _collect_emg_data(self, gesture, repeat):
        print(f"Collecting {gesture} (repetition {repeat})...")
        try:
            raw_data = self.controller.receiver.get_data()
            return process_and_validate_data(raw_data, CONFIG["data_channels"])
        except ValueError as e:
            # Display the validation error on the UI
            self.prompt_label.config(text=str(e), fg=STYLE["color_danger"])
            time.sleep(2) # Give user time to read the error
            return None
        except Exception as e:
            print(f"Error collecting {gesture} (repetition {repeat}): {e}")
            return None

    def _update_ui_for_finish(self, message="🎉 All data collection completed!"):
        self.image_label.config(image=None)
        self.prompt_label.config(text=message, fg=STYLE["color_success"])
        self.countdown_label.config(text="")
        self.btn_back.config(state="normal")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app = EMGApp()
    app.mainloop()