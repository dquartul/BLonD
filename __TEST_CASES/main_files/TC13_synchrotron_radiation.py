# Copyright 2016 CERN. This software is distributed under the
# terms of the GNU General Public Licence version 3 (GPL Version 3), 
# copied verbatim in the file LICENCE.md.
# In applying this licence, CERN does not waive the privileges and immunities 
# granted to it by virtue of its status as an Intergovernmental Organization or
# submit itself to any jurisdiction.
# Project website: http://blond.web.cern.ch/


'''
Test case for the synchrotron radiation routine.
Example for the FCC-ee at 175 GeV.

:Authors: **Juan F. Esteban Mueller**
'''

from __future__ import division
import matplotlib.pyplot as plt
import numpy as np
from input_parameters.general_parameters import GeneralParameters
from beams.beams import Beam
from beams.distributions import matched_from_distribution_density
from input_parameters.rf_parameters import RFSectionParameters
from beams.slices import Slices
from impedances.impedance import Resonators, InducedVoltageFreq, TotalInducedVoltage
from trackers.tracker import RingAndRFSection, FullRingAndRF
from synchrotron_radiation.synchrotron_radiation import SynchrotronRadiation
from scipy.constants import c, e, m_e


# SIMULATION PARAMETERS -------------------------------------------------------

# Beam parameters
particle_type = 'electron'
n_particles = int(1.7e11)          
n_macroparticles = int(1e5)
sync_momentum = 175e9 # [eV]

distribution_options = {'type':'gaussian', 'emittance': 1.0,
                        'density_variable':'density_from_J'}

# Machine and RF parameters
radius = 15915.49
gamma_transition = 377.96447
C = 2 * np.pi * radius  # [m]        
      
# Tracking details
n_turns = int(200)
n_turns_between_two_plots = 100
 
# Derived parameters
E_0 = m_e * c**2 / e    # [eV]
tot_beam_energy =  np.sqrt(sync_momentum**2 + E_0**2) # [eV]
momentum_compaction = 1 / gamma_transition**2 # [1]       

# Cavities parameters
n_rf_systems = 1                                
harmonic_numbers = [133650]                        
voltage_program = [10e9]
phi_offset = [np.pi]

bucket_length = C / c / harmonic_numbers[0]
print(bucket_length)

# DEFINE RING------------------------------------------------------------------

n_sections = 2
general_params = GeneralParameters(n_turns, np.ones(n_sections) * C/n_sections,
                                   np.tile(momentum_compaction,(1,n_sections)).T,
                                   np.tile(sync_momentum,(n_sections, n_turns+1)),
                                   particle_type, number_of_sections = n_sections)

RF_sct_par = []
for i in np.arange(n_sections)+1:
    RF_sct_par.append(RFSectionParameters(general_params, n_rf_systems, harmonic_numbers,
                          [v/n_sections for v in voltage_program], phi_offset, section_index=i) )

# DEFINE BEAM------------------------------------------------------------------

beam = Beam(general_params, n_macroparticles, n_particles)

# DEFINE TRACKER---------------------------------------------------------------
longitudinal_tracker = []
for i in range(n_sections):
    longitudinal_tracker.append(RingAndRFSection(RF_sct_par[i],beam))

full_tracker = FullRingAndRF(longitudinal_tracker)


# DEFINE SLICES----------------------------------------------------------------

number_slices = 500
slice_beam = Slices(RF_sct_par[0], beam, number_slices, cut_left = 0., 
                    cut_right = bucket_length)


# BEAM GENERATION--------------------------------------------------------------

matched_from_distribution_density(beam, full_tracker, distribution_options, 
            main_harmonic_option = 'lowest_freq')
            
slice_beam.track()

# Synchrotron radiation objects without quantum excitation
ro = 11e3
SR = []
for i in range(n_sections):
    SR.append(SynchrotronRadiation(general_params, RF_sct_par[i], beam, ro, quantum_excitation=False))

SR[0].print_SR_params()

# ACCELERATION MAP-------------------------------------------------------------

map_ = []
for i in range(n_sections):
    map_ += [longitudinal_tracker[i]] + [SR[i]]
map_ += [slice_beam]

# TRACKING + PLOTS-------------------------------------------------------------

avg_dt = np.zeros(n_turns)
std_dt = np.zeros(n_turns)

for i in range(n_turns):
    for m in map_:
        m.track()

    avg_dt[i] = np.mean(beam.dt)
    std_dt[i] = np.std(beam.dt)
        
## Fitting routines for synchrotron radiation damping
from scipy.optimize import curve_fit
def sine_exp_fit(x,y, **keywords):
    try:
        init_values = keywords['init_values']
        offset = init_values[-1]
        init_values[-1] = 0
    except:
        offset = np.mean(y)
        # omega estimation using FFT
        npoints = 12
        y_fft = np.fft.fft(y-offset, 2**npoints)
        omega_osc = 2.0*np.pi*np.abs(y_fft[:2**(npoints-1)]).argmax()/len(y_fft)/(x[1]-x[0])
        init_amp = (y.max()-y.min())/2.0
        init_omega = omega_osc
        init_values = [init_omega,0,init_amp,0,0]
    
    popt, pcov = curve_fit(sine_exp_f, x, y-offset,p0=init_values)
            
    popt[0] = np.abs(popt[0])
    popt[2] = np.abs(popt[2])
    popt[3] += offset
    if np.isinf(pcov).any():
        pcov = np.zeros([5,5])

    return popt, pcov
    
def sine_exp_f(x, omega, phi, amp, offset, tau):
    return offset + np.abs(amp)*np.sin(omega*x+phi)*np.exp(tau*x)
    
def exp_f(x, amp, offset, tau):
    return offset + np.abs(amp)*np.exp(-np.abs(tau)*x)
    
# Fit of the bunch length
plt.figure(figsize=[6,4.5])
plt.plot( 1e12*4.0*std_dt,lw=2)
a,b = popt, pcov = curve_fit(exp_f, np.arange(len(std_dt)), 4.0*std_dt)
amp, offset, tau = a[0],a[1],a[2]
plt.plot(np.arange(len(std_dt)), 1e12*exp_f(np.arange(len(std_dt)), amp, offset, np.abs(tau)),'r--',lw=2,alpha=0.75)
plt.ylim(0,plt.ylim()[1])
plt.xlabel('Turns')
plt.ylabel('Bunch length [ps]')
plt.legend(('Simulation','Damping time: {0:1.1f} turns (fit)'.format(1/np.abs(tau))),loc=0,fontsize='medium')
plt.savefig('../output_files/TC13_fig/bl_fit.png')
plt.close()


# Fit of the bunch position
a,b = sine_exp_fit(np.arange(len(avg_dt)),avg_dt)
omega, phi, amp, offset, tau = a[0],a[1],a[2],a[3],a[4]

plt.figure(figsize=[6,4.5])
plt.plot(avg_dt*1e9,lw=2)
plt.plot(np.arange(len(avg_dt)), sine_exp_f(np.arange(len(avg_dt)), omega, phi, amp, offset, tau)*1e9,'r--',lw=2,alpha=0.75)
plt.xlabel('Turns')
plt.ylabel('Bunch position [ns]')
plt.legend(('Simulation','Damping time: {0:1.1f} turns (fit)'.format(1/np.abs(tau))),loc=0,fontsize='medium')
plt.savefig('../output_files/TC13_fig/pos_fit')
plt.close()

## WITH QUANTUM EXCITATION
n_turns = 1000
# DEFINE RING------------------------------------------------------------------

n_sections = 2
general_params = GeneralParameters(n_turns, np.ones(n_sections) * C/n_sections,
                                   np.tile(momentum_compaction,(1,n_sections)).T,
                                   np.tile(sync_momentum,(n_sections, n_turns+1)),
                                   particle_type, number_of_sections = n_sections)

RF_sct_par = []
for i in np.arange(n_sections)+1:
    RF_sct_par.append(RFSectionParameters(general_params, n_rf_systems, harmonic_numbers,
                          [v/n_sections for v in voltage_program], phi_offset, section_index=i) )

# DEFINE BEAM------------------------------------------------------------------

beam = Beam(general_params, n_macroparticles, n_particles)

# DEFINE TRACKER---------------------------------------------------------------
longitudinal_tracker = []
for i in range(n_sections):
    longitudinal_tracker.append(RingAndRFSection(RF_sct_par[i],beam))

full_tracker = FullRingAndRF(longitudinal_tracker)


# DEFINE SLICES----------------------------------------------------------------

slice_beam = Slices(RF_sct_par[0], beam, number_slices, cut_left = 0., 
                    cut_right = bucket_length)


# BEAM GENERATION--------------------------------------------------------------

matched_from_distribution_density(beam, full_tracker, distribution_options, 
            main_harmonic_option = 'lowest_freq')
            
slice_beam.track()

# Redefine Synchrotron radiation objects with quantum excitation
SR = []
for i in range(n_sections):
    SR.append(SynchrotronRadiation(general_params, RF_sct_par[i], beam, ro))

# ACCELERATION MAP-------------------------------------------------------------
map_ = []
for i in range(n_sections):
    map_ += [longitudinal_tracker[i]] + [SR[i]]
map_ += [slice_beam]

# TRACKING + PLOTS-------------------------------------------------------------

std_dt = np.zeros(n_turns)
std_dE = np.zeros(n_turns)

for i in range(n_turns):
    for m in map_:
        m.track()

    std_dt[i] = np.std(beam.dt)    
    std_dE[i] = np.std(beam.dE) 

plt.figure(figsize=[6,4.5])
plt.plot(1e-6*std_dE, lw=2)
plt.plot(np.arange(len(std_dE)), [1e-6*SR[0].sigma_dE*sync_momentum] * len(std_dE), 'r--', lw=2)
print('Equilibrium energy spread = {0:1.3f} [MeV]'.format(1e-6*std_dE[-10:].mean()))
plt.xlabel('Turns')
plt.ylabel('Energy spread [MeV]')
plt.savefig('../output_files/TC13_fig/std_dE_QE.png')
plt.close()

plt.figure(figsize=[6,4.5])
plt.plot(1e12*4.0*std_dt, lw=2)
print('Equilibrium bunch length = {0:1.3f} [ps]'.format(4e12*std_dt[-10:].mean()))
plt.xlabel('Turns')
plt.ylabel('Bunch length [ps]')
plt.savefig('../output_files/TC13_fig/bl_QE.png')
plt.close()

print("Done!")