# FieldBot
This repository houses the code pertaining to the field sonar data collection rigs in the lab. This code is slightly modified from the batbot6(.5) code to use a single microphone, and post processing tools (coming soon). 

**Note: These data collection rigs work AS IS. Please DO NOT remove any parts for other projects, as we need functioning sonar devices that we can deploy on short notice**

## Jetson install, and required dependencies
Go [here -- GitHub](https://github.com/Qengineering/Jetson-Nano-Ubuntu-20-image), and download the NVIDIA Jetson OS image. I would recommend scrolling down on the GitHub page and find the "bare image" download, unless you will be running TensorFlow and PyTorch on the jetson. Note that this is image is a modified version of the official NVIDIA image which allows the jetson to run a newer version of Ubuntu (20.04), which is required to install newer python versions.

Flash the image with [etcher](https://etcher.balena.io) to an SD card with a capacity >= 128 GB.

Once inserting the SD card and booting, the jetson should launch into a live OS. At this point, I would recommend going into the settings and changing the locales since the default is not US standard. 

See [here -- GitHub](https://github.com/BIST-Research) to see how to connect to eduroam

The default password for the jetson is ```jetson```. The username is also ```jetson``` and the hostname is ```nano```

Once connected to the internet, run an apt update and upgrade:

```sudo apt update && apt upgrade -y```

Now reboot:

```sudo reboot```

Install some preliminary dependencies:

```sudo apt install curl gparted```

Now, run ```gparted```, which should open a graphical interface for disk management. It should tell you that there is alot of unallocated space which can be added to the live OS. Follow the prompt and apply the changes.

Next, add the follwing apt repository, which will allow us to install python3.12:

```sudo add-apt-repository ppa:deadsnakes/ppa```

And run a repo source update:

```sudo apt update```

Now install python3.12:

```sudo apt install python3.12 python3.12-dev python3-pip```




