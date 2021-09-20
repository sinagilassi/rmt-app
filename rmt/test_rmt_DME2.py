# TEST
# STATIC MODELING
# ----------------

# REVIEW
# check unit
# flowrate [mol/s]
# rate formation [mol/m^3.s]

# import packages/modules
import numpy as np
import math
import json
from data import *
from core import constants as CONST
from rmt import rmtExe
from core.utilities import roundNum
from docs.rmtUtility import rmtUtilityClass as rmtUtil


# operating conditions
# pressure [Pa]
P = 5*1e6
# temperature [K]
T = 523
# operation period [s]
opT = 50

# set feed mole fraction
# H2/COx ratio
H2COxRatio = 1
# CO2/CO ratio
CO2COxRatio = 0.5
feedMoFr = setFeedMoleFraction(H2COxRatio, CO2COxRatio)
# print(f"feed mole fraction: {feedMoFr}")

# mole fraction
MoFri0 = np.array([feedMoFr[0], feedMoFr[1], feedMoFr[2],
                   feedMoFr[3], feedMoFr[4], feedMoFr[5]])
# print(f"component mole fraction: {y0}")

# concentration [kmol/m3]
ct0 = calConcentration(feedMoFr, P, T)
# print(f"component concentration: {ct0}")

# total concentration [kmol/m3]
ct0T = calTotalConcentration(ct0)
# print(f"total concentration: {ct0T}")

# inlet fixed bed superficial gas velocity [m/s]
SuGaVe = 0.2
# inlet fixed bed interstitial gas velocity [m/s]
InGaVe = SuGaVe/bed_por
# flux [kmol/m2.s] -> total concentration x superficial velocity
Fl0 = ct0T*SuGaVe
# print(f"feed flux: {Ft0}")

# cross section of reactor x porosity [m^2]
rea_CSA = rmtUtil.reactorCrossSectionArea(bed_por, rea_D)
# real flowrate @ P & T [m^3/s]
VoFlRa = InGaVe*rea_CSA
#  flowrate at STP [m^3/s]
VoFlRaSTP = rmtUtil.volumetricFlowrateSTP(VoFlRa, P, T)
#  molar flowrate @ ideal gas [mol/s]
MoFlRa0 = rmtUtil.VoFlRaSTPToMoFl(VoFlRaSTP)
#  initial concentration[mol/m3]
Ct0 = MoFlRa0/VoFlRa
# molar flux
MoFl0 = MoFlRa0/(rea_CSA/bed_por)
# or
MoFl0_2 = Ct0*InGaVe*bed_por

# component all
compList = ["H2", "CO2", "H2O", "CO", "CH3OH", "DME"]

# reactions
reactionSet = {
    "R1": "CO2 + 3H2 <=> CH3OH + H2O",
    "R2": "CO + H2O <=> H2 + CO2",
    "R3": "2CH3OH <=> DME + H2O",
}

reactionRateSet = {
    "R1": "T+ P + y + 1",
    "R2": "T+ P + y + 2",
    "R3": "T+ P + y + 3",
}


# NOTE
# reactor
# reactor volume [m^3]
ReVo = 5
# reactor length [m]
ReLe = rea_L
# reactor inner diameter [m]
# ReInDi = math.sqrt(ReVo/(ReLe*CONST.PI_CONST))
ReInDi = rea_D
# particle dimeter [m]
PaDi = cat_d
# particle density [kg/m^3]
CaDe = cat_rho
# particle specific heat capacity [kJ/kg.K]
CaSpHeCa = cat_Cp/1000

# NOTE
# external heat
# overall heat transfer coefficient [J/m^2.s.K]
U = 50
# effective heat transfer area per unit of reactor volume [m^2/m^3]
a = 4/ReInDi
# medium temperature [K]
Tm = 523
# Ua
Ua = U*a
#
externalHeat = {
    "OvHeTrCo": U,
    "EfHeTrAr": a,
    "MeTe": Tm
}

# gas mixture viscosity [Pa.s]
GaMiVi = 1e-5

# NOTE
# reaction rates
# initial values
varis0 = {
    # parameters
    "RT":  "CONST.R_CONST*T",
    #  kinetic constant
    # DME production
    #  [kmol/kgcat.s.bar2]
    "K1":  "35.45*math.exp(-1.7069e4/rDict['VARS']['RT'])",
    #  [kmol/kgcat.s.bar]
    "K2":  "7.3976*math.exp(-2.0436e4/rDict['VARS']['RT'])",
    #  [kmol/kgcat.s.bar]
    "K3":  "8.2894e4*math.exp(-5.2940e4/rDict['VARS']['RT'])",
    # adsorption constant [1/bar]
    "KH2":  "0.249*math.exp(3.4394e4/rDict['VARS']['RT'])",
    "KCO2":  "1.02e-7*math.exp(6.74e4/rDict['VARS']['RT'])",
    "KCO":  "7.99e-7*math.exp(5.81e4/rDict['VARS']['RT'])",
    #  equilibrium constant
    "Ln_KP1":  "4213/T - 5.752 * \
        math.log(T) - 1.707e-3*T + 2.682e-6 * \
        (math.pow(T, 2)) - 7.232e-10*(math.pow(T, 3)) + 17.6",
    "KP1":  "math.exp(rDict['VARS']['Ln_KP1'])",
    "log_KP2":  "2167/T - 0.5194 * \
        math.log10(T) + 1.037e-3*T - 2.331e-7*(math.pow(T, 2)) - 1.2777",
    "KP2":  "math.pow(10, rDict['VARS']['log_KP2'])",
    "Ln_KP3":  "4019/T + 3.707 * \
        math.log(T) - 2.783e-3*T + 3.8e-7 * \
        (math.pow(T, 2)) - 6.56e-4/(math.pow(T, 3)) - 26.64",
    "KP3":  "math.exp(rDict['VARS']['Ln_KP3'])",
    # partial pressure
    #  partial pressure of H2 [bar]
    "PH2":  "P*(rDict['PARAMS']['yi_H2'])*1e-5",
    #  partial pressure of CO2 [bar]
    "PCO2":  "P*(rDict['PARAMS']['yi_CO2'])*1e-5",
    #  partial pressure of H2O [bar]
    "PH2O":  "P*(rDict['PARAMS']['yi_H2O'])*1e-5",
    #  partial pressure of CO [bar]
    "PCO":  "P*(rDict['PARAMS']['yi_CO'])*1e-5",
    #  partial pressure of CH3OH [bar]
    "PCH3OH":  "P*(rDict['PARAMS']['yi_CH3OH'])*1e-5",
    #  partial pressure of CH3OCH3 [bar]
    "PCH3OCH3":  "P*(rDict['PARAMS']['yi_DME'])*1e-5",
    # reaction rates
    "ra1":  "rDict['VARS']['PCO2']*rDict['VARS']['PH2']",
    "ra2":  "1 + (rDict['VARS']['KCO2']*rDict['VARS']['PCO2']) + (rDict['VARS']['KCO']*rDict['VARS']['PCO']) + math.sqrt(rDict['VARS']['KH2']*rDict['VARS']['PH2'])",
    "ra3":  "(1/rDict['VARS']['KP1'])*((rDict['VARS']['PH2O']*rDict['VARS']['PCH3OH'])/(rDict['VARS']['PCO2']*(math.pow(rDict['VARS']['PH2'], 3))))",
    "ra4":  "rDict['VARS']['PH2O'] - (1/rDict['VARS']['KP2'])*((rDict['VARS']['PCO2']*rDict['VARS']['PH2'])/rDict['VARS']['PCO'])",
    "ra5":  "(math.pow(rDict['VARS']['PCH3OH'], 2)/rDict['VARS']['PH2O'])-(rDict['VARS']['PCH3OCH3']/rDict['VARS']['KP3'])",
}

# parameter dict
params0 = {
    #  mole fraction
    "yi_H2": MoFri0[0],
    "yi_CO2": MoFri0[1],
    "yi_H2O": MoFri0[2],
    "yi_CO": MoFri0[3],
    "yi_CH3OH": MoFri0[4],
    "yi_DME": MoFri0[5]
}

# reaction rates
rates0 = {
    "r1":  "rDict['VARS']['K1']*(rDict['VARS']['ra1']/(math.pow(rDict['VARS']['ra2'], 3)))*(1-rDict['VARS']['ra3'])*CaBeDe",
    "r2":  "rDict['VARS']['K2']*(1/rDict['VARS']['ra2'])*rDict['VARS']['ra4']*CaBeDe",
    "r3":  "rDict['VARS']['K3']*rDict['VARS']['ra5']*CaBeDe"
}

# reaction rate
reactionRateSet = {
    "PARAMS": params0,
    "VARS": varis0,
    "RATES": rates0
}


# NOTE
# model input - feed
modelInput = {
    "model": "M1",
    "operating-conditions": {
        "pressure": P,
        "temperature": T,
        "period": opT
    },
    "feed": {
        "mole-fraction": MoFri0,
        "molar-flowrate": MoFlRa0,
        "molar-flux": MoFl0,
        "volumetric-flowrate": VoFlRa,
        "concentration": ct0,
        "mixture-viscosity": GaMiVi,
        "components": {
            "shell": compList,
            "tube": [],
            "medium": []
        }
    },
    "reactions": reactionSet,
    "reaction-rates": reactionRateSet,
    "external-heat": externalHeat,
    "reactor": {
        "ReInDi": ReInDi,
        "ReLe": ReLe,
        "PaDi": PaDi,
        "BeVoFr": bed_por,
        "CaBeDe": bulk_rho,
        "CaDe": CaDe,
        "CaSpHeCa": CaSpHeCa
    }
}

# run exe
res = rmtExe(modelInput)
# print(f"modeling result: {res}")

# save modeling result
# with open('res.json', 'w') as f:
#     json.dump(res, f)

# steady-state results
# concentration
# total concentration
ssModelingData = res['resModel']['dataYs']

# save modeling result [txt]
# np.savetxt('ssModeling.txt', ssModelingData, fmt='%.10e')
# load
# c = np.loadtxt('ssModeling.txt', dtype=np.float64)
# print("c: ", c, " c Shape: ", c.shape)

# save binary file
np.save('ResM1.npy', ssModelingData)
# load
# b2Load = np.load('res3.npy')
# print("b2Load: ", b2Load, b2Load.shape)
