#!/usr/bin/env python

###############################################################################
## This simple example shows how to do a sweep device (sd) capture and plotting.
##
## To run this:
##     <your OS python command> <example_file>.py <device_IP>
##
## © ThinkRF Corporation 2020. All rights reserved.
###############################################################################
#%%
from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepDevice

import sys
import time
import math

from matplotlib.pyplot import plot, figure, axis, xlabel, ylabel, show
import numpy as np

# declare sweep constants
RBW = 100e3
RFE_MODE = 'SH'

# create an RTSA instance
dut = WSA()

# get device's IP and connect
# if len(sys.argv) > 1:
#     ip = sys.argv[1]
# else:
#     ip, ok = QtGui.QInputDialog.getText(win, 'Open Device',
#                 'Enter a hostname or IP address:')
ip='169.254.16.253'
dut.connect(ip)


# get data acquisition permission
dut.request_read_perm()

dut.configure_flattening(loaded=None)


# get some properties, such as min & max frequencies of the RTSA
START_FREQ = 1.2e9
STOP_FREQ = 1.4e9

# declare sweep device
sd = SweepDevice(dut)

# read the spectral data
fstart, fstop, spectral_data = sd.capture_power_spectrum(START_FREQ, STOP_FREQ,
    RBW, device_settings={'rfe_mode':RFE_MODE, 'attenuator':0},
    mode = RFE_MODE, continuous=False)
print(f"Got spectral data from {fstart} to {fstop} with {len(spectral_data)} samples")

# setup the graph & plot
fig = figure(1)
xvalues = np.linspace(fstart, fstop, len(spectral_data))
xlabel("Frequency (Hz)")
ylabel("Amplitude (dBm)")
plot(xvalues, spectral_data, color='blue')

# show graph
show()

#%%
len(spectral_data)

#%%
sd._vrt_receive(sd.real_device.read())