#!/usr/bin/env python

###############################################################################
## This example shows how to do channel power computation on the spectral data.
## The full spectral data is used here; however, user could pass the range
## of interest of the 'spectral_data' into calculate_channel_power() instead.
##
## To run this:
##     <your OS python command> <example_file>.py <device_IP>
##
## © ThinkRF Corporation 2020. All rights reserved.
###############################################################################

from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepDevice
from pyrf.numpy_util import calculate_channel_power

import sys
import time
import math

from matplotlib.pyplot import plot, figure, axis, xlabel, ylabel, show
import numpy as np

# a method for Video BW smoothing
def smooth(list,degree=1):
    new_list = []
    list_average = np.mean(sorted(list)[int(0.995 * len(list)):-1]) + 5
    for n, i in enumerate(list):

        start = max(0, n - degree)
        stop = min(len(list), n + degree)
        points = list[start:stop]
        if list[n] > list_average:
            new_list.append(list[n])
        else:
            new_list.append(np.mean(points))

    return new_list

# declare sweep constants
RBW = 100e3
VBW = 100e3
RFE_MODE = 'SH'

# create an RTSA instance
dut = WSA()

# connect to an RTSA
dut.connect(sys.argv[1])

# get some properties
START_FREQ = dut.properties.MIN_FREQ
STOP_FREQ = dut.properties.MAX_TUNABLE[RFE_MODE]

# get data acquisition permission
dut.request_read_perm()

# does not apply flattenting to show simple plotting & calculation
dut.configure_flattening(loaded=None)

# declare sweep device
sd = SweepDevice(dut)

# read the spectral data
fstart, fstop, spectral_data = sd.capture_power_spectrum(START_FREQ, STOP_FREQ,
    RBW, device_settings={'rfe_mode':RFE_MODE, 'attenuator':0},
    mode = RFE_MODE, continuous=False)

# apply the VBW algorithm
spectral_data = smooth(spectral_data, max(1, RBW/VBW))

# calculate the channel power
channel_power = calculate_channel_power(spectral_data)
print(f"Channel Power: {channel_power} dBm")

# plot the spectral data
fig = figure(1)
xvalues = np.linspace(fstart, fstop, len(spectral_data))
xlabel(f"Frequency (Hz)\nChannel Power: {channel_power} dBm")
ylabel("Amplitude (dBm)")
plot(xvalues, spectral_data, color='blue')

# show graph
show()
