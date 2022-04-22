###################
# This example uses the SweepDevice class to capture data
# This method is preferred if you want to use bandwidth larger than 40 MHz
# note that natively, pyrf does not give an option to do averaging when using the SweepDevice
# we have modified the capture_power_spectrum function in SweepDevice so it does averaging 
# we implemented this averaging the same way as in capture_spectrum function (which uses block capture)
# TO FIX : Currently, there is an issue wherein we get gibberish when trying to 
# read numeric values after setting up the device. To reproduce the error, 
# sweepdev = SweepDevice(dut)
# print(dut.freq())
# the spectrum capturing still works fine
###################

#%%
# import required libraries
import numpy as np
from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepDevice, SweepSettings
from pyrf.util import capture_spectrum

from time import time
import matplotlib.pyplot as plt
from pyrf.vrt import vrt_packet_reader
#%%
RFE_MODE = 'SH'
START_FREQ = 5.5e9
STOP_FREQ = 6.5e9
CENTER_FREQ = 6e9 
SPP = 32 * 512
PPB = 1
RBW = 125e6 / (SPP * PPB * 24)  # 125 MHz is the sampling rate
ATTENUATION = 20
GAIN = 'HIGH'
AVERAGE = 50
DECIMATION = 1 # no decimation

span = STOP_FREQ-START_FREQ
#%%
dut = WSA()
dut.connect('169.254.16.253')

dut.reset()
#dut.request_read_perm()
dut.psfm_gain(GAIN)
#%%
sweepdev = SweepDevice(dut) ## numeric values start being gibberish after this point, but the spectrum capture works fine
#%%
#avglist = [1,5,10,50,100,500,1000,5000,10000]
#timelist = []
#for avg in avglist:
startT = time()
fstart, fstop, spectra_data = sweepdev.capture_power_spectrum(START_FREQ,
                                STOP_FREQ,
                                RBW,
                                {'attenuator':ATTENUATION},
                                mode = RFE_MODE,
                                niter=1,
                                average = AVERAGE)
freq_range = np.linspace(fstart , fstop, len(spectra_data))
stopT = time()
print(f"Averages = {AVERAGE}, time = {stopT-startT:2.2f} sec")
plt.plot(freq_range,spectra_data, label = 'Sweep capture')

#timelist.append(stopT-startT)
# %%
atten = sweepdev.real_device.attenuator()
print(atten)
