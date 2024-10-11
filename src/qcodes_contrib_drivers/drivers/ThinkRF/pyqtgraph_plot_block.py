#!/usr/bin/env python

###############################################################################
## This example makes use of capture_spectrum() of util.py to perform a single
## block capture of desire RBW and plot the computed spectral data within the
## usable frequency range.
##
## See thinkrf.py for other data capture functions, especially if
## raw data capture (with context info output) is preferred
##
## Note: Spectral flattening is not applied in this simple example.
##
## To run this:
##     <your OS python command> <example_file>.py <device_IP>
##
## © ThinkRF Corporation 2020. All rights reserved.
###############################################################################

#%% import required libraries
import matplotlib.pyplot as plt
import numpy as np
from pyrf.devices.thinkrf import WSA
from pyrf.flattening import calibration_vectors
from pyrf.util import capture_spectrum
from pyrf.config import TriggerSettings

# Constants for configuration
RFE_MODE = 'HDR'
CENTER_FREQ = 1250 * 1e6
RBW = 1000e3
AVERAGE = 100
DECIMATION = 1
ATTENUATION = 0
GAIN = 'HIGH'
TRIGGER_SETTING = {'type': 'LEVEL',
                'fstart': CENTER_FREQ-50e6, # some value
                'fstop': CENTER_FREQ+50e6,  # some value
                'amplitude': -100}

# initialize an RTSA (aka WSA) device handle
dut = WSA()

ip='169.254.16.253'
dut.connect(ip)

# initialize RTSA configurations
if (RFE_MODE != 'DD'):
    dut.reset()

dut.request_read_perm()

dut.rfe_mode(RFE_MODE)
if (RFE_MODE != 'DD'):
    dut.freq(CENTER_FREQ)
dut.attenuator(ATTENUATION)
dut.psfm_gain(GAIN)
# dut.trigger(TRIGGER_SETTING)


fstart, fstop, pow_data = capture_spectrum(dut, RBW, AVERAGE, DECIMATION)
fs = np.linspace( fstart, fstop, pow_data.size )
plt.figure()
plt.plot(fs,pow_data)
#%%
(fstop-fstart)/1e3
