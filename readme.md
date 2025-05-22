# NxBCI

 If you want to use NxBCI locally, please follow the steps below.
 
 ## Set up the runtime environment

It is recommended that you use Anaconda to build a runtime environment, and you can [download](https://www.anaconda.com/download) Anaconda here.

1. Build the environment with Anaconda

    - Download this project to your local hard drive
    - Open the Anaconda Prompt window and go to the EEG_APP project directory, then enter the following command:
    ```
        conda env create -f environment.yml
    ```
    It may take some time for the third-party dependencies of the environment to be downloaded, so please be patient

    
2. install NxBCI
    - Enter the command below to install the NxBCI
    ```
        pip install -e .
    ```