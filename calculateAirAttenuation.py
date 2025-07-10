import numpy as np
import matplotlib.pyplot as plt

def air_attenuation(f, T=293.15, hr=0.5, P0=101.325):
    """Calculate air attenuation in dB/m using ISO 9613-1 standard"""
    T01 = 273.16
    F = -6.8346 * (T01/T)**1.261 + 4.6151
    Psat = 10**F
    h = hr * Psat / P0
    frO = 24 + 4.04e4 * h * (0.02 + h) / (0.391 + h)
    frN = (293.15/T)**0.5 * (9 + 280 * h * np.exp(-4.17*((293.15/T)**(1/3) - 1)))
    term1 = 1.84e-11 * (293.15/T)**0.5
    term2 = 0.1068 * np.exp(-3352/T) * frN / (frN**2 + f**2) * (293.15/T)**2.5
    term3 = 0.01278 * np.exp(-2239.1/T) * frO / (frO**2 + f**2) * (293.15/T)**2.5
    return 8.686 * f**2 * (term1 + term2 + term3)

# Generate data
freqs = np.linspace(30000, 100000, 500)
atten = air_attenuation(freqs)

# Plot configuration
plt.figure(figsize=(8, 4))
plt.plot(freqs/1000, atten, 'b-', linewidth=2)
plt.title("Air Attenuation (20°C, 50% RH)")
plt.xlabel("Frequency (kHz)")
plt.ylabel("Attenuation (dB/m)")
plt.grid(True)
plt.tight_layout()
plt.show()
