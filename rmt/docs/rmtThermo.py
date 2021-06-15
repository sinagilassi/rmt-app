# THERMODYNAMIC RELATIONS
# ------------------------

# import packages/modules
import numpy as np
import re
from core.constants import Tref
from data.componentData import heatCapacityAtConstatPresureList, standardHeatOfFormationList


def main():
    pass


def calHeatCapacityAtConstantPressure(comList, T):
    """
        cal: heat capacity at constant pressure
        unit: [kJ/kmol.K] 

        args:
            comList: component name list
            T: temperature [K]
    """
    # try/except
    try:
        # heat capacity
        _Cpi = []

        # heat capacity data
        loadData = heatCapacityAtConstatPresureList

        for i in comList:
            # fun expr
            CpiData = [item['Cp'] for item in loadData if i == item['symbol']]
            # fun
            def cpFun(T): return eval(CpiData[0])
            # fun exe
            CpiVal = cpFun(T)
            # store
            _Cpi.append(CpiVal)

        # convert to numpy array
        Cpi = np.array(_Cpi)
        # res
        return Cpi
    except Exception as e:
        print(e)


def calMixtureHeatCapacityAtConstantPressure(MoFri, HeCaCoPri):
    """
        cal: heat capacity at constant pressure of mixture
        unit: [kJ/kmol.K] 
    """
    # try/except
    try:
        # check
        MoFriSize = np.size(MoFri)
        HeCaCoPriSize = np.size(HeCaCoPri)

        if MoFriSize != HeCaCoPriSize:
            raise

        # dot multiplication
        CpMix = np.dot(MoFri, HeCaCoPri)
        # res
        return CpMix
    except Exception as e:
        print(e)


def calEnthalpyChange(comList, T2, T1=Tref):
    """
        cal: enthalpy change
        unit: [kJ/kmol] 

        args:
            comList: component name list
            T2: final temperature [K]
            T1: reference temperature [K]
        return:
            dH: enthalpy change between T1 and T2
    """
    # try/except
    try:
        # cp at T1 [kJ/kmol.K]
        CpT1 = calHeatCapacityAtConstantPressure(comList, T1)
        # cp at T2 [kJ/kmol.K]
        CpT2 = calHeatCapacityAtConstantPressure(comList, T2)
        # cp average
        CpAvg = (CpT1 + CpT2)*0.50

        # enthalpy change [kJ/kmol]
        dH = CpAvg*(T2 - T1)
        # res
        return dH
    except Exception as e:
        print(e)


def calStandardEnthalpyOfReaction(reaExpr):
    """
        cal: standard enthalpy of reaction at 25C
        unit: [kJ/mol]

        args:
            reaExpr: reaction expression:  
                    A + B <=> C + D

        return:
            standard heat of reaction [kJ/kmol]
    """
    # try/except
    try:
        # analyze reactions
        reaType = reaExpr.replace("<", "").replace(">", "")
        # reactant/products list
        compR = reaType.replace(r" ", "").split("=")
        print(f"compR1 {compR}")

        # componets
        reactantList = re.findall(r"([0-9.]*)([a-zA-Z0-9.]+)", compR[0])
        print(f"reactantList {reactantList}")
        productList = re.findall(r"([0-9.]*)([a-zA-Z0-9.]+)", compR[1])
        print(f"productList {productList}")

        # standard heat of formation at 25
        _dHf25iReactantList = []
        _dHf25iProductList = []

        # load data
        loadData = standardHeatOfFormationList

        # reactant
        for i in reactantList:
            # fun expr
            dHf25iData = [item['dHf25']*float(i[0]) if len(i[0]) != 0 else item['dHf25']*1
                          for item in loadData if i[1] == item['symbol']]
            # store
            _dHf25iReactantList.append(dHf25iData)

        # products
        for i in productList:

            # fun expr
            dHf25iData = [item['dHf25']*float(i[0]) if len(i[0]) != 0 else item['dHf25']*1
                          for item in loadData if i[1] == item['symbol']]
            # store
            _dHf25iProductList.append(dHf25iData)

        # conversion
        dHf25iReactantList = np.array(_dHf25iReactantList).flatten()
        dHf25iProductList = np.array(_dHf25iProductList).flatten()

        # standard heat of formation at 25 [kJ/kmol]
        dHf25 = (np.sum(dHf25iProductList) -
                 np.sum(dHf25iReactantList))/1000.00
        # res
        return dHf25
    except Exception as e:
        print(e)


def calHeatOfReaction(dHf25, dH):
    """
        cal: enthalpy of reaction at T
        unit:[kJ/kmol]

        args:
            dHf25: standard heat of reaction at 25C [kJ/kmol]
            dH: enthalpy of reaction [kJ/kmol]
    """
    # try/except
    try:
        # heat of reaction
        dHr = dHf25 + dH
        # res
        return dHr
    except Exception as e:
        print(e)


def calSpaceVelocity(VoFlRa, ReVo):
    """
        cal: space velocity [1/s]

        args:
            VoFlRa: volumetric flowrate [m^3/s]
            ReVo: reactor volume [m^3]

    """
    # try/except
    try:
        SpVe = VoFlRa/ReVo
        # res
        return SpVe
    except Exception as e:
        print(e)


def calGasHourlySpaceVelocity(VoFlRa, ReVo):
    """
        cal: gas hourly space velocity [1/h]

        args:
            VoFlRa: volumetric flowrate [m^3/h]
            ReVo: reactor volume [m^3]

    """
    # try/except
    try:
        GaHoSpVe = VoFlRa/ReVo
        # res
        return GaHoSpVe
    except Exception as e:
        print(e)
