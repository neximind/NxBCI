from collections import deque
import time
import math
import logging

logger = logging.getLogger()

class Receiver:
    
    def __init__(self,channels = 16,sample_rate =500,duration = 4):
        self.data_queues = [deque(maxlen=sample_rate*duration) for _ in range(channels)]
        self.num_channels = channels
        self.duration = duration
        self.sample_rate = sample_rate
        self.isReceiving = False

    def get_data(self):
        start_time = time.time()
        self.isReceiving = True
        for j in range(50):
            t = start_time + j * 0.01  # 假设每次循环增加0.01秒
            for i in range(self.num_channels):
                y = 50.0 * math.sin(2.0 * math.pi * 5.0 * t)
                self.data_queues[i].append(y)
        return self.data_queues

    def stop(self):
        logger.info("[Receiver Base] Receiver base called stopping functions.")

    def __del__(self):
        logger.info("[Receiver Base] Receiver base was destroyed!!!")