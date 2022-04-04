#####################################################################
## This example makes use of capture_spectrum() of util.py to
## perform a single block capture of desire RBW and plot the
## computed spectral data within the usuable frequency range
##
## See thinkrf.py for other data capture functions, especially if
## raw data capture (with context info output) is preferred
#####################################################################
#%%
# import required libraries
import matplotlib.pyplot as plt
import numpy as np
from pyrf.devices.thinkrf import WSA
from pyrf.util import capture_spectrum
import time

# # Constants for configuration
# RFE_MODE = 'SH'
# CENTER_FREQ = 5.12e9
# SPP = 16384
# PPB = 1
# RBW = 5e3 / (SPP * PPB)  # 125 MHz is the sampling rate
# AVERAGE = 10
# DECIMATION = 1 # no decimation
# ATTENUATION = 0
# GAIN = 'HIGH'
# TRIGGER_SETTING = {'type': 'NONE',
#                 'fstart': (CENTER_FREQ - 2e6), # some value
#                 'fstop': (CENTER_FREQ + 2e6),  # some value
#                 'amplitude': -100}


RFE_MODE = 'SH' 
CENTER_FREQ = 6e9 #5.881e9 # - 100e6
SPP = 32*512
PPB = 1
RBW = 125e6 / (SPP * PPB * 2)  # 125 MHz is the sampling rate
AVERAGE = 5000
DECIMATION = 1 # no decimation
ATTENUATION = 20
GAIN = 'HIGH'
TRIGGER_SETTING = {'type': 'NONE',
                'fstart': (CENTER_FREQ - 1e6), # some value
                'fstop': (CENTER_FREQ + 1e6),  # some value
                'amplitude': -100}
REFLEVEL = None

# initialize an RTSA (aka WSA) device handle
dut = WSA()

dut.connect('169.254.16.253')

#%% initialize RTSA configurations
dut.reset()
dut.request_read_perm()
dut.rfe_mode(RFE_MODE)
dut.freq(CENTER_FREQ)
dut.attenuator(ATTENUATION)
dut.psfm_gain(GAIN)
dut.trigger(TRIGGER_SETTING)


avglist = [1,5,10,50,100,500,1000,5000,10000]
timelist = []

#for avg in avglist:
startT = time.time()
fstart, fstop, pow_data = capture_spectrum(dut, RBW, AVERAGE, DECIMATION)
freq_range = np.linspace(fstart , fstop, len(pow_data))
stopT = time.time()
# plt.plot( freq_range, pow_data )
print(f"Averages = {AVERAGE}, time = {stopT-startT:2.2f} sec")
#   timelist.append(stopT-startT)
#%%
len(pow_data)
#%%
plt.plot(freq_range,pow_data)
#%%
span = 40e6
fbegin = CENTER_FREQ - span/2
fend = CENTER_FREQ + span/2
keep = (  fbegin <  freq_range ) & ( freq_range < fend )
#plt.plot( freq_range[keep], pow_data[keep] )
plt.plot( np.linspace(fbegin, fend, len(pow_data[keep])), pow_data[keep] )
ax = plt.gca()
ax.set_xlabel('f (Hz)')
ax.set_ylabel('Power (dBm)')
# %%
plt.plot(avglist, timelist, '--x')
plt.xlabel("N Averages")
plt.ylabel("Time [s]")
    
# %%
