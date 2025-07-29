<font color=#40A0D0 size=6>

# NxBCI Electroencephalogram (EEG)/Electromyography (EMG) Acquisition system

</font>

<div align=center>
<img src="https://github.com/neximind/NxBCI/blob/main/media/image/nxbci_1.png" height="600" width=auto >
</div>

## Project Introduction:
NxBCI aims to construct an EEG/EMG data collection system that can be used for research, education, and consumer electronic products. The device features 16 channels, each with a resolution of 24 bits and a sampling rate of up to 4 kHz. With a low-noise front-end amplifier, it can achieve an effective resolution of 10 ppm (parts per million) within a measurement range of 3 mVpp, along with a noise characteristic (equivalent input) of less than 1µVpp (0.2 µV RMS). Additionally, the kit includes 2.4G Wi-Fi for data output (TCP or MQTT), Bluetooth for setup control, and access to secondary sensor data. Furthermore, it has a TF slot for offline data collection mode, which is sufficient to support a 24-hour HOLTER mode when configured with a large-capacity lithium battery. The device also features two expansion interfaces (USB-A and 4pin UART/IIC) for connecting external accelerometer-gyroscope-magnetometer components, isolated UART communication modules, and other expansion devices. The USB-Type C interface includes a charging management circuit and programming/debugging port for DIY users to customize extensively.

## Spec Sheet:
Parameters|unit|minimum|typical|maximum
|---|---|---|---|---|
Sampling rate | SPS|500|1000|4000*
noise floor|uVrms|-|0.16|-
-3DB frequency range | Hz|0.1|150|1.5K*
Resolution | Bits|24|24|24
Full Scale Range|mVpp|3|3|30*

Connection mode:

* Local TCP connection;
* Cloud MQTT;
* Offline recording to TF Card;
* Connect to other devices via isolated UART interface**

Power Supply Mode:

* 5000mAH flat lithium-ion battery;
* 4 x 18650 cylindrical lithium-ion batteries;
* 6 AA alkaline batteries, or NiMH batteries;


Expansion interface:

* USB type A Host;
* 2.54mm 4PIN interface for IIC/UART communication with expansion devices;

Additional functions:

* GPS***;

*In EMG mode

**Extended option support required

***GPS is optional according to local laws

## Disclaimer:
1. As this device will directly connect electrically with the human body, safety is its primary consideration. Therefore, under any circumstances, the device should remain floating (i.e., connected only to the target under test). If it is to be connected as a sub-device to other equipment, reliable isolation devices must be employed for communication. It is prohibited to connect the device to a human body while it is charging; doing so could result in it becoming connected to the mains electrical supply if the charger fails, <font color=#FF0000>which could lead to fatal consequences</font>. It is the user's responsibility to be aware of the relevant safety regulations regarding biopotential signal measurements. Please ensure that you are familiar with the pertinent knowledge before use.

2. This device is not intended for medical purposes, and its data should not be considered as medical reference.

3. This device has not yet obtained UN38.3 certification. Please ensure that you can manage the potential <font color=#FF0000>risks of battery runaway combustion or explosion</font>, and comply with local regulations regarding the transport of lithium battery-powered electronic devices.

## Typical Applications:

NxBCI is a multi-channel bioelectrical signal acquisition device, you can use the data it generates to do all kinds of interesting things, and in the process, you can actually come into contact with a lot of numerical analysis tools and AI algorithms, which may make your course less painful ;）

Here are some possible use cases:

1. Sleep quality analysis.
2. Muscle movement and rehabilitation testing, (such as smart fitness equipment.) 
3. EMG control systems (such as game peripherals).
4. Observation of ECG (for non-medical purposes).
5. EEG control systems such as MI and SSVEP.
6. Electrical impedance imaging.
7. Animal movement analysis.

## Technical documentation：

[NxBCI hardware user manual](https://www.github.com)

[More about NxBCI](https://github.com/neximind/NxBCI/blob/main/More%20About%20NxBCI/More_About_%20NxBCI_en.md)

[How to purchase NxBCI accessories.](https://www.github.com)

[NxBCI software user manual]( https://github.com/neximind/NxBCI/blob/main/Software%20Documents/IOS/NxBCI_User_Manual.md)

## Apps:
[Windows]( https://github.com/neximind/NxBCI/releases/tag/v1.0.0-preview)<br>
[MacOS]( https://www.github.com)<br>
[IOS]( https://www.github.com)<br>
**Android** is under development now.<br>

## SDK:
[NxBCI SDK]( https://github.com/neximind/NxBCI/tree/main/PythonSDK)

## Measured Data:

1. Input the noise characteristics after the short circuit (X1000)

<div align=center>
    <img src="https://github.com/neximind/NxBCI/blob/main/media/image/test_fig_1.png" height="400" width=auto >
</div>

2. Utilize a signal generator to produce a sine wave with a frequency of 10Hz and a peak-to-peak voltage of 10µV as the input signal for the EasyBCI device, focusing on its time-domain characteristics.
<div align=center>
    <img src="https://github.com/neximind/NxBCI/blob/main/media/image/test_fig_2.png" height="400" width=auto >
</div>

3. Grip the electrodes to measure the electrocardiogram.                
<div align=center>
    <img src="https://github.com/neximind/NxBCI/blob/main/media/image/test_fig_3.png" height="400" width=auto >
</div>

4. Alpha waves of subjects in the states of closed eyes and open eyes.

closed eyes：
<div align=center>
    <img src="https://github.com/neximind/NxBCI/blob/main/media/image/test_fig_4.png" height="600" width=auto >
</div>

open eyes：
<div align=center>
    <img src="https://github.com/neximind/NxBCI/blob/main/media/image/test_fig_5.png" height="600" width=auto >
</div>

5. SSVEP 7Hz response：
<div align=center>
    <img src="https://github.com/neximind/NxBCI/blob/main/media/image/test_fig_6.png" height="600" width=auto >
</div>

6. SSVEP Video of the testing process.
<div align=center>
    <a href="https://youtu.be/watch?v=TlHIAkXt1_o">
        <img src="http://img.youtube.com/vi/TlHIAkXt1_o/0.jpg" alt="SSVEP Video of the testing process.">
    </a>
</div>

7. Alpha Video of the testing process.

<div align=center>
    <a href="https://youtu.be/watch?v=Y4VIpdCZ8LY">
        <img src="http://img.youtube.com/vi/Y4VIpdCZ8LY/0.jpg" alt="Alpha Video of the testing process.">
    </a>
</div>

9. sEMG Video of the testing process. （using ios App）

<div align=center>
    <a href="https://youtu.be/watch?v=LbqRUQPh_qw">
        <img src="http://img.youtube.com/vi/LbqRUQPh_qw/0.jpg" alt="sEMG Video of the testing process. （using ios App）">
    </a>
</div>

## Team and Values:

We are electronic enthusiasts from a gaming company, driven by great curiosity and passion for technology. However, due to the high cost of commercially available BCI products, we decided to create an affordable alternative ourselves. After rigorous experimentation, we discovered that the audio ADC is surprisingly robust (we even utilized it for an acoustic camera, which will be unveiled shortly). Therefore, this led to our current solution. Due to the lack of professional equipment, we cannot guarantee that this device will achieve the performance of the ADS1299 solution. If you are looking for professional equipment backed by a chip manufacturer, please choose the ADS1299 or an equivalent solution. If you possess sufficient testing capability to provide us with comparative test data, we would be extremely grateful. Our aim in creating this device is to enable more curious children to realize their ideas, such as applications that use EMG data to control prosthetic limbs, potentially helping those in need.

## We Look Forward to Your Participation:

As the specific applications have exceeded our capabilities, the best choice is to open the platform for everyone to participate in its development. We have established a platform for communication where you can inform us of new ideas, suggestions for modifications, issues encountered, and more. We sincerely look forward to your attention and participation.

[NxBCI Discussion Group](https://www.github.com)

## Future Plans:

Our team aims to raise sufficient funds for mold development, in order to replace the current 3D printed casing, and to further research support for expandable accessories. A portion of the funds will also be allocated to continue the acoustic camera project. We hope for your understanding and support to present you with greater surprises.This is the acoustic camera, currently in the prototype stage.

<div align=center>
<img src="https://github.com/neximind/NxBCI/blob/main/media/image/oac_1.png" height="400" width=auto >
<img src="https://github.com/neximind/NxBCI/blob/main/media/image/oac_0.png" height="400" width=auto >
<img src="https://github.com/neximind/NxBCI/blob/main/media/image/oac_2.png" height="400" width=auto >
</div>
