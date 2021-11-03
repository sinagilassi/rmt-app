# PACKED-BED REACTOR MODEL
# -------------------------

# import packages/modules
import math as MATH
import numpy as np
from numpy.lib import math
from library.plot import plotClass as pltc
from scipy.integrate import solve_ivp
from timeit import default_timer as timer
from scipy.optimize import fsolve
from scipy import optimize
# internal
from .modelSetting import MODEL_SETTING, PROCESS_SETTING
from .rmtUtility import rmtUtilityClass as rmtUtil
from .rmtThermo import *
from .fluidFilm import *
from .rmtReaction import reactionRateExe, componentFormationRate
from .gasTransPor import calTest
from core.errors import errGeneralClass as errGeneral
from data.inputDataReactor import *
from core import constants as CONST
from core.utilities import roundNum, selectFromListByIndex
from core.config import REACTION_RATE_ACCURACY
from solvers.solSetting import solverSetting
from core.eqConstants import CONST_EQ_Sh
from solvers.solOrCo import OrCoClass
from solvers.solCatParticle import OrCoCatParticleClass
from solvers.solFiDi import FiDiBuildCMatrix, FiDiBuildTMatrix, FiDiSetMatrix, FiDiBuildCMatrix_DiLe, FiDiBuildTMatrix_DiLe
from solvers.solFiDi import FiDiMeshGenerator, FiDiDerivative1, FiDiDerivative2, FiDiNonUniformDerivative1, FiDiNonUniformDerivative2
from solvers.odeSolver import AdBash3, PreCorr3
from solvers.solResultAnalysis import setOptimizeRootMethod, sortedResult3


class PackedBedHomoReactorClass:
    # def main():
    """
    Packed-bed Reactor Homogenous Model
    M1 model: packed-bed plug-flow model (1D model)
        assumptions:
            homogeneous
            no dispersion/diffusion along the reactor length
            no radial variation of concentration and temperature
            mass balance is based on flux
            ergun equation is used for pressure drop
            neglecting gravitational effects, kinetic energy, and viscosity change
    M2 model: dynamic homogenous modeling
    M3 model: steady-state homogenous modeling
    """
    # internal data
    _internalData = []

    def __init__(self, modelInput, internalData, reactionListSorted, reactionStochCoeffList):
        self.modelInput = modelInput
        self.internalData = internalData
        self.reactionListSorted = reactionListSorted
        self.reactionStochCoeffList = reactionStochCoeffList

    # @property
    # def internalData(cls):
    #     return cls._internalData

    # @internalData.setter
    # def internalData(cls, value):
    #     cls._internalData.clear()
    #     cls._internalData.extend(value)

    def runM10(self):
        """
        M1 modeling case
        """

        # operating conditions
        P = self.modelInput['operating-conditions']['pressure']
        T = self.modelInput['operating-conditions']['temperature']
        # ->
        modelParameters = {
            "pressure": P,
            "temperature": T
        }

        # component list
        compList = self.modelInput['feed']['components']['shell']
        labelList = compList.copy()
        labelList.append("Flux")

        # initial values
        # -> mole fraction
        MoFri = self.modelInput['feed']['mole-fraction']
        # -> flux [kmol/m^2.s]
        MoFl = self.modelInput['feed']['molar-flux']
        IV = []
        IV.extend(MoFri)
        IV.append(MoFl)
        # print(f"IV: {IV}")

        # time span
        # t = (0.0, rea_L)
        t = np.array([0, rea_L])
        times = np.linspace(t[0], t[1], 20)
        # tSpan = np.linspace(0, rea_L, 25)

        # ode call
        sol = solve_ivp(PackedBedReactorClass.modelEquationM1,
                        t, IV, method="LSODA", t_eval=times, args=(P, T))

        # ode result
        successStatus = sol.success
        dataX = sol.t
        dataYs = sol.y

        # check
        if successStatus is True:
            # plot setting
            XYList = pltc.plots2DSetXYList(dataX, dataYs)
            # -> label
            dataList = pltc.plots2DSetDataList(XYList, labelList)
            # plot result
            pltc.plots2D(dataList, "Reactor Length (m)",
                         "Concentration (mol/m^3)", "1D Plug-Flow Reactor")

        else:
            XYList = []
            dataList = []

        # return
        res = {
            "XYList": XYList,
            "dataList": dataList
        }

        return res

# NOTE
# steady-state homogenous modeling

    def runM1(self):
        """
        M1 modeling case
        steady-state modeling of plug-flow reactor
        unknowns: Fi,F*,T,P
        """
        # start computation
        start = timer()

        # solver setting
        solverConfig = self.modelInput['solver-config']
        solverIVPSet = solverConfig['ivp']

        # operating conditions
        P = self.modelInput['operating-conditions']['pressure']
        T = self.modelInput['operating-conditions']['temperature']

        # reaction list
        reactionDict = self.modelInput['reactions']
        reactionList = rmtUtil.buildReactionList(reactionDict)

        # component list
        compList = self.modelInput['feed']['components']['shell']

        # graph label setting
        labelList = compList.copy()
        labelList.append("Flux")
        labelList.append("Temperature")
        labelList.append("Pressure")

        # component no
        compNo = len(compList)
        indexFlux = compNo
        indexTemp = indexFlux + 1
        indexPressure = indexTemp + 1

        # reactor spec
        ReSpec = self.modelInput['reactor']
        # reactor inner diameter [m]
        ReInDi = ReSpec['ReInDi']
        # reactor length [m]
        ReLe = ReSpec['ReLe']
        # cross-sectional area [m^2]
        CrSeAr = CONST.PI_CONST*(ReInDi ** 2)/4
        # particle diameter [m]
        PaDi = ReSpec['PaDi']
        # bed porosity (bed void fraction)
        BeVoFr = ReSpec['BeVoFr']

        # mole fraction
        MoFri = np.array(self.modelInput['feed']['mole-fraction'])
        # flowrate [mol/s]
        MoFlRa = self.modelInput['feed']['molar-flowrate']
        # component flowrate [mol/s]
        MoFlRai = MoFlRa*MoFri
        # flux [mol/m^2.s]
        MoFl = MoFlRa/(CrSeAr)
        # component flux [mol/m^2.s]
        MoFli = MoFl*MoFri

        # component molecular weight [g/mol]
        MoWei = rmtUtil.extractCompData(self.internalData, "MW")

        # external heat
        ExHe = self.modelInput['external-heat']
        # cooling temperature [K]
        Tm = ExHe['MeTe']
        # overall heat transfer coefficient [J/s.m2.K]
        U = ExHe['OvHeTrCo']
        # heat transfer area over volume [m2/m3]
        a = 4/ReInDi  # ExHe['EfHeTrAr']

        # gas mixture viscosity [Pa.s]
        GaMiVi = self.modelInput['feed']['mixture-viscosity']

        # reaction rate expression
        reactionRateExpr = self.modelInput['reaction-rates']

        # var no (Fi,FT,T,P)
        varNo = compNo + 3

        # initial values
        IV = np.zeros(varNo)
        IV[0:compNo] = MoFlRai
        IV[indexFlux] = MoFl
        IV[indexTemp] = T
        IV[indexPressure] = P
        # print(f"IV: {IV}")

        # parameters
        # component data
        reactionListSorted = self.reactionListSorted
        # reaction coefficient
        reactionStochCoeff = self.reactionStochCoeffList

        # standard heat of reaction at 25C [kJ/kmol]
        StHeRe25 = np.array(
            list(map(calStandardEnthalpyOfReaction, reactionList)))

        # fun parameters
        FunParam = {
            "compList": compList,
            "const": {
                "CrSeAr": CrSeAr,
                "MoWei": MoWei,
                "StHeRe25": StHeRe25,
                "GaMiVi": GaMiVi
            },
            "ReSpec": ReSpec,
            "ExHe": {
                "OvHeTrCo": U,
                "EfHeTrAr": a,
                "MeTe": Tm
            },
            "reactionRateExpr": reactionRateExpr
        }

        # save data
        timesNo = solverSetting['S3']['timesNo']

        # time span
        # t = (0.0, rea_L)
        t = np.array([0, ReLe])
        t_span = np.array([0, ReLe])
        times = np.linspace(t_span[0], t_span[1], timesNo)
        # tSpan = np.linspace(0, rea_L, 25)

        # solver selection
        # BDF, Radau, LSODA
        solverIVP = "LSODA" if solverIVPSet == 'default' else solverIVPSet

        # ode solver call
        sol = solve_ivp(PackedBedHomoReactorClass.modelEquationM1,
                        t, IV, method=solverIVP, t_eval=times, args=(reactionListSorted, reactionStochCoeff, FunParam))

        # ode result
        successStatus = sol.success
        dataX = sol.t
        # all results
        dataYs = sol.y
        # molar flowrate [mol/s]
        dataYs1 = sol.y[0:compNo, :]
        labelListYs1 = labelList[0:compNo]
        # REVIEW
        # convert molar flowrate [mol/s] to mole fraction
        dataYs1_Ftot = np.sum(dataYs1, axis=0)
        dataYs1_MoFri = dataYs1/dataYs1_Ftot
        # flux
        dataYs2 = sol.y[indexFlux, :]
        labelListYs2 = labelList[indexFlux]
        # temperature
        dataYs3 = sol.y[indexTemp, :]
        labelListYs3 = labelList[indexTemp]
        # pressure
        dataYs4 = sol.y[indexPressure, :]

        # FIXME
        # build matrix
        _dataYs = np.concatenate(
            (dataYs1_MoFri, [dataYs2], [dataYs3], [dataYs4]), axis=0)
        # steady-state results [mole fraction, temperature]
        _ssdataYs = np.concatenate(
            (dataYs1_MoFri, [dataYs3]), axis=0)

        # NOTE
        # end of computation
        end = timer()
        elapsed = roundNum(end - start)

        # plot info
        plotTitle = f"Steady-State Modeling [M1] with timesNo: {timesNo} within {elapsed} seconds"

        # check
        if successStatus is True:
            # plot setting: build (x,y) series
            XYList = pltc.plots2DSetXYList(dataX, _dataYs)
            # -> add label
            dataList = pltc.plots2DSetDataList(XYList, labelList)
            # datalists
            dataLists = [dataList[0:compNo],
                         dataList[indexFlux], dataList[indexTemp], dataList[indexPressure]]
            # select datalist
            _dataListsSelected = selectFromListByIndex([0, -2], dataLists)
            # subplot result
            pltc.plots2DSub(_dataListsSelected, "Reactor Length (m)",
                            "Concentration (mol/m^3)", plotTitle)

            # plot result
            # pltc.plots2D(dataList[0:compNo], "Reactor Length (m)",
            #              "Concentration (mol/m^3)", "1D Plug-Flow Reactor")

            # pltc.plots2D(dataList[indexFlux], "Reactor Length (m)",
            #              "Flux (kmol/m^2.s)", "1D Plug-Flow Reactor")

            # pltc.plots2D(dataList[indexTemp], "Reactor Length (m)",
            #              "Temperature (K)", "1D Plug-Flow Reactor")

        else:
            # error
            print(f"Final result: {successStatus}")
            _dataYs = []
            XYList = []
            dataList = []

        # return
        res = {
            "dataYs": _ssdataYs,
            "XYList": XYList,
            "dataList": dataList
        }

        return res

    def modelEquationM1(t, y, reactionListSorted, reactionStochCoeff, FunParam):
        """
            M1 model
            mass, energy, and momentum balance equations
            modelParameters:
                reactionListSorted: reactant/product and coefficient lists
                reactionStochCoeff: reaction stoichiometric coefficient
                FunParam:
                    compList: component list
                    const
                        CrSeAr: reactor cross sectional area [m^2]
                        MoWei: component molecular weight [g/mol]
                        StHeRe25: standard heat of reaction at 25C [kJ/kmol] | [J/mol]
                        GaMiVi: gas mixture viscosity [Pa.s]
                    ReSpec: reactor spec
                    ExHe: exchange heat spec
                        OvHeTrCo: overall heat transfer coefficient [J/m^2.s.K]
                        EfHeTrAr: effective heat transfer area [m^2]
                        MeTe: medium temperature [K]
                    reactionRateExpr: reaction rate expression
                        PARAMS, VARS, RATES

        """
        # fun params
        # component symbol list
        comList = FunParam['compList']
        # const ->
        const = FunParam['const']
        # cross-sectional area [m^2]
        CrSeAr = const['CrSeAr']
        # component molecular weight [g/mol]
        MoWei = const['MoWei']
        # standard heat of reaction at 25C [kJ/kmol] | [J/mol]
        StHeRe25 = const['StHeRe25']
        # gas viscosity [Pa.s]
        GaMiVi = const['GaMiVi']
        # reactor spec ->
        ReSpec = FunParam['ReSpec']
        # bed porosity (bed void fraction)
        BeVoFr = ReSpec['BeVoFr']
        # bulk density (catalyst bed density)
        CaBeDe = ReSpec['CaBeDe']
        # particle diameter [m]
        PaDi = ReSpec['PaDi']
        # exchange heat spec ->
        ExHe = FunParam['ExHe']
        # reaction rate expressions
        reactionRateExpr = FunParam['reactionRateExpr']
        # using equation
        varisSet = reactionRateExpr['VARS']
        ratesSet = reactionRateExpr['RATES']

        # components no
        # y: component molar flowrate, total molar flux, temperature, pressure
        compNo = len(comList)
        indexFlux = compNo
        indexT = indexFlux + 1
        indexP = indexT + 1

        # molar flowrate list [mol/m^3]
        MoFlRai = y[0:compNo]
        # total molar flux [mol/m^2.s]
        MoFl = y[indexFlux]
        # temperature [K]
        T = y[indexT]
        # pressure [Pa]
        P = y[indexP]

        # total flowrate [mol/m^3]
        MoFlRa = np.sum(MoFlRai)

        # volumetric flowrate [m^3/s]
        VoFlRai = calVolumetricFlowrateIG(P, T, MoFlRai)

        # concentration species [mol/m^3]
        CoSpi = calConcentrationIG(MoFlRai, VoFlRai)
        # total concentration [mol/m^3]
        CoSp = np.sum(CoSpi)

        # mole fraction
        MoFri = rmtUtil.moleFractionFromConcentrationSpecies(CoSpi)
        # MoFri2 = rmtUtil.moleFractionFromConcentrationSpecies(MoFlRai)

        # interstitial gas velocity [m/s]
        InGaVe = rmtUtil.calSuperficialGasVelocityFromEOS(MoFl, P, T)
        # superficial gas velocity [m/s]
        SuGaVe = InGaVe*BeVoFr

        # mixture molecular weight [kg/mol]
        MiMoWe = rmtUtil.mixtureMolecularWeight(MoFri, MoWei, "kg/mol")

        # gas density [kg/m^3]
        GaDe = calDensityIG(MiMoWe, CoSp)
        GaDeEOS = calDensityIGFromEOS(P, T, MiMoWe)

        # ergun equation
        ergA = 150*GaMiVi*SuGaVe/(PaDi**2)
        ergB = ((1-BeVoFr)**2)/(BeVoFr**3)
        ergC = 1.75*GaDe*(SuGaVe**2)/PaDi
        ergD = (1-BeVoFr)/(BeVoFr**3)
        RHS_ergun = -1*(ergA*ergB + ergC*ergD)

        # NOTE
        # kinetics
        # component formation rate [mol/m^3.s]
        # conversion
        # FIXME
        # Ri2 = 1000*np.array(PackedBedReactorClass.modelReactions(
        #     P, T, MoFri, CaBeDe))

        # loop
        loopVars0 = (T, P, MoFri, CoSpi)

        # component formation rate [mol/m^3.s]
        # check unit
        RiLoop = np.array(reactionRateExe(
            loopVars0, varisSet, ratesSet))
        Ri = np.copy(RiLoop)

        # component formation rate [mol/m^3.s]
        # rf[mol/kgcat.s]*CaBeDe[kgcat/m^3]
        # ri = np.zeros(compNo)
        # for k in range(compNo):
        #     # reset
        #     _riLoop = 0
        #     for m in range(len(reactionStochCoeff)):
        #         for n in range(len(reactionStochCoeff[m])):
        #             if comList[k] == reactionStochCoeff[m][n][0]:
        #                 _riLoop += reactionStochCoeff[m][n][1]*Ri[m]
        #         ri[k] = _riLoop

        # call [mol/m^3.s]
        ri = componentFormationRate(
            compNo, comList, reactionStochCoeff, Ri)

        # overall formation rate [mol/m^3.s]
        OvR = np.sum(ri)

        # enthalpy
        # heat capacity at constant pressure of mixture Cp [kJ/kmol.K] | [J/mol.K]
        # Cp mean list
        CpMeanList = calMeanHeatCapacityAtConstantPressure(comList, T)
        # print(f"Cp mean list: {CpMeanList}")
        # Cp mixture
        CpMeanMixture = calMixtureHeatCapacityAtConstantPressure(
            MoFri, CpMeanList)
        # print(f"Cp mean mixture: {CpMeanMixture}")

        # enthalpy change from Tref to T [kJ/kmol] | [J/mol]
        # enthalpy change
        EnChList = np.array(calEnthalpyChangeOfReaction(reactionListSorted, T))
        # heat of reaction at T [kJ/kmol] | [J/mol]
        HeReT = np.array(EnChList + StHeRe25)
        # overall heat of reaction [J/m^3.s]
        OvHeReT = np.dot(Ri, HeReT)

        # cooling temperature [K]
        Tm = ExHe['MeTe']
        # overall heat transfer coefficient [J/s.m2.K]
        U = ExHe['OvHeTrCo']
        # heat transfer area over volume [m2/m3]
        a = ExHe['EfHeTrAr']
        # heat transfer parameter [W/m^3.K] | [J/s.m^3.K]
        Ua = U*a
        # external heat [J/m^3.s]
        Qm = rmtUtil.calHeatExchangeBetweenReactorMedium(
            Tm, T, U, a, 'J/m^3.s')

        # diff/dt
        dxdt = []
        # loop vars
        # FIXME
        # const_F1 = 1/(CrSeAr*BeVoFr)
        const_F1 = 1/(CrSeAr)
        const_T1 = MoFl*CpMeanMixture
        const_T2 = MoFlRa*CpMeanMixture/CrSeAr

        # mass balance (molar flowrate) [mol/s]
        for i in range(compNo):
            dxdt_F = (1/const_F1)*ri[i]
            dxdt.append(dxdt_F)
        # flux
        dxdt_Fl = OvR
        dxdt.append(dxdt_Fl)

        # energy balance (temperature) [K]
        dxdt_T = (1/const_T1)*(-OvHeReT + Qm)
        dxdt.append(dxdt_T)

        # momentum balance (ergun equation)
        dxdt_P = RHS_ergun
        dxdt.append(dxdt_P)

        return dxdt

# NOTE
# dynamic homogenous modeling

    def runM2(self):
        """
        M2 modeling case
        dynamic model
        unknowns: Ci, T (dynamic), P (static)
        """
        # NOTE
        # start computation
        start = timer()

        # solver setting
        solverConfig = self.modelInput['solver-config']
        solverIVPSet = solverConfig['ivp']

        # operating conditions
        P = self.modelInput['operating-conditions']['pressure']
        T = self.modelInput['operating-conditions']['temperature']
        # operation time [s]
        opT = self.modelInput['operating-conditions']['period']

        # reaction list
        reactionDict = self.modelInput['reactions']
        reactionList = rmtUtil.buildReactionList(reactionDict)
        # number of reactions
        reactionListNo = len(reactionList)

        # reaction rate expression
        reactionRateExpr = self.modelInput['reaction-rates']

        # component list
        compList = self.modelInput['feed']['components']['shell']

        # graph label setting
        labelList = compList.copy()
        labelList.append("Temperature")
        # labelList.append("Pressure")

        # component no
        compNo = len(compList)
        indexTemp = compNo
        indexPressure = indexTemp + 1

        # reactor spec
        ReSpec = self.modelInput['reactor']
        # reactor inner diameter [m]
        ReInDi = ReSpec['ReInDi']
        # reactor length [m]
        ReLe = ReSpec['ReLe']
        # cross-sectional area [m^2]
        CrSeAr = CONST.PI_CONST*(ReInDi ** 2)/4
        # particle diameter [m]
        PaDi = ReSpec['PaDi']
        # bed void fraction - porosity
        BeVoFr = ReSpec['BeVoFr']

        ## inlet values ##
        # inlet volumetric flowrate at T,P [m^3/s]
        VoFlRa0 = self.modelInput['feed']['volumetric-flowrate']
        # inlet species concentration [kmol/m^3]
        SpCoi0 = np.array(self.modelInput['feed']['concentration'])
        # inlet total concentration [kmol/m^3]
        SpCo0 = np.sum(SpCoi0)

        # component molecular weight [g/mol]
        MoWei = rmtUtil.extractCompData(self.internalData, "MW")

        # external heat
        ExHe = self.modelInput['external-heat']

        # gas mixture viscosity [Pa.s]
        GaMiVi = self.modelInput['feed']['mixture-viscosity']

        # finite difference points in the z direction
        zNo = solverSetting['S2']['zNo']
        # length list
        dataXs = np.linspace(0, ReLe, zNo)
        # element size - dz [m]
        dz = ReLe/(zNo-1)

        # var no (Ci,T)
        varNo = compNo + 1
        # concentration var no
        varNoCon = compNo*zNo
        # temperature var no
        varNoTemp = 1*zNo
        # total var no along the reactor length
        varNoT = varNo*zNo

        # initial values at t = 0 and z >> 0
        IVMatrixShape = (varNo, zNo)
        IV2D = np.zeros(IVMatrixShape)
        # initialize IV2D
        # -> concentration [kmol/m^3]
        for i in range(compNo):
            for j in range(zNo):
                IV2D[i][j] = SpCoi0[i]

        for j in range(zNo):
            IV2D[indexTemp][j] = T

        # flatten IV
        IV = IV2D.flatten()

        # print(f"IV: {IV}")

        # parameters
        # component data
        reactionListSorted = self.reactionListSorted
        # reaction coefficient
        reactionStochCoeff = self.reactionStochCoeffList

        # standard heat of reaction at 25C [kJ/kmol]
        StHeRe25 = np.array(
            list(map(calStandardEnthalpyOfReaction, reactionList)))

        # fun parameters
        FunParam = {
            "compList": compList,
            "const": {
                "CrSeAr": CrSeAr,
                "MoWei": MoWei,
                "StHeRe25": StHeRe25,
                "GaMiVi": GaMiVi,
                "zNo": zNo,
                "varNo": varNo,
                "varNoT": varNoT,
                "reactionListNo": reactionListNo,
                "dz": dz
            },
            "ReSpec": ReSpec,
            "ExHe": ExHe,
            "reactionRateExpr": reactionRateExpr,
            "constBC1": {
                "VoFlRa0": VoFlRa0,
                "SpCoi0": SpCoi0,
                "SpCo0": SpCo0,
                "P0": P,
                "T0": T
            }
        }

        # time span
        tNo = solverSetting['S2']['tNo']
        opTSpan = np.linspace(0, opT, tNo + 1)

        # save data
        timesNo = solverSetting['S2']['timesNo']

        # result
        dataPack = []

        # build data list
        # over time
        dataPacktime = np.zeros((varNo, tNo, zNo))

        # solver selection
        # BDF, Radau, LSODA
        solverIVP = "LSODA" if solverIVPSet == 'default' else solverIVPSet

        # time loop
        for i in range(tNo):
            # set time span
            t = np.array([opTSpan[i], opTSpan[i+1]])
            times = np.linspace(t[0], t[1], timesNo)
            print(f"time: {t} seconds")

            # ode call
            sol = solve_ivp(PackedBedHomoReactorClass.modelEquationM2,
                            t, IV, method=solverIVP, t_eval=times, args=(reactionListSorted, reactionStochCoeff, FunParam))

            # ode result
            successStatus = sol.success
            # check
            if successStatus is False:
                raise

            # time interval
            dataTime = sol.t
            # all results
            dataYs = sol.y

            # component concentration [mol/m^3]
            dataYs1 = dataYs[0:varNoCon, -1]
            # 2d matrix
            dataYs1_Reshaped = np.reshape(dataYs1, (compNo, zNo))
            # REVIEW
            # convert concentration to mole fraction
            dataYs1_Ctot = np.sum(dataYs1_Reshaped, axis=0)
            dataYs1_MoFri = dataYs1_Reshaped/dataYs1_Ctot
            # temperature - 2d matrix
            dataYs2 = np.array([dataYs[varNoCon:varNoT, -1]])

            # combine
            _dataYs = np.concatenate((dataYs1_MoFri, dataYs2), axis=0)

            # save data
            dataPack.append({
                "successStatus": successStatus,
                "dataTime": dataTime[-1],
                "dataYCons": dataYs1_Reshaped,
                "dataYTemp": dataYs2,
                "dataYs": _dataYs
            })

            for m in range(varNo):
                # var list
                dataPacktime[m][i, :] = dataPack[i]['dataYs'][m, :]

            # update initial values [IV]
            IV = dataYs[:, -1]

        # NOTE
        # end of computation
        end = timer()
        elapsed = roundNum(end - start)

        # NOTE
        # steady-state result
        # txt
        # ssModelingResult = np.loadtxt('ssModeling.txt', dtype=np.float64)
        # binary
        # ssModelingResult = np.load('ResM1.npy')
        # ssdataXs = np.linspace(0, ReLe, zNo)
        # ssXYList = pltc.plots2DSetXYList(dataXs, ssModelingResult)
        # ssdataList = pltc.plots2DSetDataList(ssXYList, labelList)
        # datalists
        # ssdataLists = [ssdataList[0:compNo],
        #                ssdataList[indexTemp]]
        # subplot result
        # pltc.plots2DSub(ssdataLists, "Reactor Length (m)",
        #                 "Concentration (mol/m^3)", "1D Plug-Flow Reactor")

        # plot info
        plotTitle = f"Dynamic Modeling [M2] for opT: {opT} with zNo: {zNo}, tNo: {tNo}"

        # REVIEW
        # display result at specific time
        for i in range(tNo):
            # var list
            _dataYs = dataPack[i]['dataYs']
            # plot setting: build (x,y) series
            XYList = pltc.plots2DSetXYList(dataXs, _dataYs)
            # -> add label
            dataList = pltc.plots2DSetDataList(XYList, labelList)
            # datalists
            dataLists = [dataList[0:compNo],
                         dataList[indexTemp]]
            if i == tNo-1:
                # subplot result
                pltc.plots2DSub(dataLists, "Reactor Length (m)",
                                "Concentration (mol/m^3)", plotTitle)

        # REVIEW
        # display result within time span
        _dataListsLoop = []
        _labelNameTime = []

        for i in range(varNo):
            # var list
            _dataPacktime = dataPacktime[i]
            # plot setting: build (x,y) series
            XYList = pltc.plots2DSetXYList(dataXs, _dataPacktime)
            # -> add label
            # build label
            for t in range(tNo):
                _name = labelList[i] + " at t=" + str(opTSpan[t+1])

                _labelNameTime.append(_name)

            dataList = pltc.plots2DSetDataList(XYList, _labelNameTime)
            # datalists
            _dataListsLoop.append(dataList[0:tNo])
            # reset
            _labelNameTime = []

        # select items
        # indices = [0, 2, -1]
        # selected_elements = [_dataListsLoop[index] for index in indices]
        # select datalist
        _dataListsSelected = selectFromListByIndex([1, -1], _dataListsLoop)

        # subplot result
        # pltc.plots2DSub(_dataListsSelected, "Reactor Length (m)",
        #                 "Concentration (mol/m^3)", "Dynamic Modeling of 1D Plug-Flow Reactor")

        # return
        res = {
            "XYList": XYList,
            "dataList": dataList
        }

        return res

    def modelEquationM2(t, y, reactionListSorted, reactionStochCoeff, FunParam):
        """
            M2 model [dynamic modeling]
            mass, energy, and momentum balance equations
            modelParameters:
                reactionListSorted: reactant/product and coefficient lists
                reactionStochCoeff: reaction stoichiometric coefficient
                FunParam:
                    compList: component list
                    const
                        CrSeAr: reactor cross sectional area [m^2]
                        MoWei: component molecular weight [g/mol]
                        StHeRe25: standard heat of reaction at 25C [kJ/kmol] | [J/mol]
                        GaMiVi: gas mixture viscosity [Pa.s]
                        zNo: number of finite difference in the z direction
                        varNo: number of variables (Ci, CT, T)
                        varNoT: number of variables in the domain (zNo*varNoT)
                        reactionListNo: reaction list number
                        dz: differential length [m]
                    ReSpec: reactor spec
                    ExHe: exchange heat spec
                        OvHeTrCo: overall heat transfer coefficient [J/m^2.s.K]
                        EfHeTrAr: effective heat transfer area [m^2]
                        MeTe: medium temperature [K]
                    reactionRateExpr: reaction rate expression
                    constBC1:
                        VoFlRa0: inlet volumetric flowrate [m^3/s],
                        SpCoi0: species concentration [kmol/m^3],
                        SpCo0: total concentration [kmol/m^3]
                        P0: inlet pressure [Pa]
                        T0: inlet temperature [K]

        """
        # fun params
        # component symbol list
        comList = FunParam['compList']
        # const ->
        const = FunParam['const']
        # cross-sectional area [m^2]
        CrSeAr = const['CrSeAr']
        # component molecular weight [g/mol]
        MoWei = const['MoWei']
        # standard heat of reaction at 25C [kJ/kmol] | [J/mol]
        StHeRe25 = const['StHeRe25']
        # gas viscosity [Pa.s]
        GaMiVi = const['GaMiVi']
        # reaction no
        reactionListNo = const['reactionListNo']
        # dz [m]
        dz = const['dz']
        # reactor spec ->
        ReSpec = FunParam['ReSpec']
        # particle diameter [m]
        PaDi = ReSpec['PaDi']
        # bed void fraction - porosity
        BeVoFr = ReSpec['BeVoFr']
        # bulk density (catalyst bed density)
        CaBeDe = ReSpec['CaBeDe']
        # catalyst density [kgcat/m^3 of particle]
        CaDe = ReSpec['CaDe']
        # catalyst heat capacity at constant pressure [kJ/kg.K]
        CaSpHeCa = ReSpec['CaSpHeCa']

        # exchange heat spec ->
        ExHe = FunParam['ExHe']

        # reaction rate expressions
        reactionRateExpr = FunParam['reactionRateExpr']
        # using equation
        varisSet = reactionRateExpr['VARS']
        ratesSet = reactionRateExpr['RATES']

        # zNo
        zNo = const['zNo']
        # var no.
        varNo = const['varNo']
        # var no. in the domain
        varNoT = const['varNoT']

        # boundary conditions constants
        constBC1 = FunParam['constBC1']
        ## inlet values ##
        # inlet volumetric flowrate at T,P [m^3/s]
        VoFlRa0 = constBC1['VoFlRa0']
        # inlet species concentration [kmol/m^3]
        SpCoi0 = constBC1['SpCoi0']
        # inlet total concentration [kmol/m^3]
        SpCo0 = constBC1['SpCo0']
        # inlet pressure [Pa]
        P0 = constBC1['P0']
        # inlet temperature [K]
        T0 = constBC1['T0']

        # calculate
        # molar flowrate [kmol/s]
        MoFlRa0 = SpCo0*VoFlRa0
        # superficial gas velocity [m/s]
        InGaVe0 = VoFlRa0/(CrSeAr*BeVoFr)
        # interstitial gas velocity [m/s]
        SuGaVe0 = InGaVe0*BeVoFr

        # superficial gas velocity [m/s]
        InGaVeList_z = np.zeros(zNo)
        InGaVeList_z[0] = InGaVe0

        # total molar flux [kmol/m^2.s]
        MoFl_z = np.zeros(zNo)
        MoFl_z[0] = MoFlRa0

        # reaction rate
        Ri_z = np.zeros((zNo, reactionListNo))

        # pressure [Pa]
        P_z = np.zeros(zNo + 1)
        P_z[0] = P0

        # components no
        # y: component molar flowrate, total molar flux, temperature, pressure
        compNo = len(comList)
        indexT = compNo
        indexP = indexT + 1

        # species concentration [kmol/m^3]
        CoSpi = np.zeros(compNo)

        # reaction rate
        ri = np.zeros(compNo)

        # NOTE
        # distribute y[i] value through the reactor length
        # reshape
        yLoop = np.reshape(y, (varNo, zNo))

        # -> concentration [mol/m^3]
        SpCoi_z = np.zeros((compNo, zNo))
        for i in range(compNo):
            _SpCoi = yLoop[i, :]
            SpCoi_z[i, :] = _SpCoi

        # temperature [K]
        T_z = np.zeros(zNo)
        T_z = yLoop[indexT, :]

        # diff/dt
        # dxdt = []
        # matrix
        dxdtMat = np.zeros((varNo, zNo))

        # NOTE
        # FIXME
        # define ode equations for each finite difference [zNo]
        for z in range(zNo):
            ## block ##

            # FIXME
            # concentration species [kmol/m^3]
            for i in range(compNo):
                _SpCoi_z = SpCoi_z[i][z]
                CoSpi[i] = max(_SpCoi_z, CONST.EPS_CONST)

            # total concentration [kmol/m^3]
            CoSp = np.sum(CoSpi)

            # temperature [K]
            T = T_z[z]
            # pressure [Pa]
            P = P_z[z]

            ## calculate ##
            # mole fraction
            MoFri = np.array(
                rmtUtil.moleFractionFromConcentrationSpecies(CoSpi))

            # gas velocity based on interstitial velocity [m/s]
            InGaVe = rmtUtil.calGaVeFromEOS(InGaVe0, SpCo0, CoSp, P0, P)
            # superficial gas velocity [m/s]
            SuGaVe = InGaVe*BeVoFr

            # total flowrate [kmol/s]
            # [kmol/m^3]*[m/s]*[m^2]
            MoFlRa = CoSp*SuGaVe*CrSeAr
            # molar flowrate list [kmol/s]
            MoFlRai = MoFlRa*MoFri
            # convert to [mol/s]
            MoFlRai_Con1 = 1000*MoFlRai

            # molar flux [kmol/m^2.s]
            MoFl = MoFlRa/CrSeAr

            # volumetric flowrate [m^3/s]
            VoFlRai = calVolumetricFlowrateIG(P, T, MoFlRai_Con1)

            # mixture molecular weight [kg/mol]
            MiMoWe = rmtUtil.mixtureMolecularWeight(MoFri, MoWei, "kg/mol")

            # gas density [kg/m^3]
            GaDe = calDensityIG(MiMoWe, CoSp)
            GaDeEOS = calDensityIGFromEOS(P, T, MiMoWe)

            # NOTE
            # ergun equation
            ergA = 150*GaMiVi*SuGaVe/(PaDi**2)
            ergB = ((1-BeVoFr)**2)/(BeVoFr**3)
            ergC = 1.75*GaDe*(SuGaVe**2)/PaDi
            ergD = (1-BeVoFr)/(BeVoFr**3)
            RHS_ergun = -1*(ergA*ergB + ergC*ergD)

            # momentum balance (ergun equation)
            dxdt_P = RHS_ergun
            # dxdt.append(dxdt_P)
            P_z[z+1] = dxdt_P*dz + P_z[z]

            # NOTE
            # REVIEW
            ## kinetics ##
            # net reaction rate expression [kmol/m^3.s]
            # rf[kmol/kgcat.s]*CaBeDe[kgcat/m^3]
            # SpCoi conversion
            _SpCoi = 1e3*CoSpi
            # loop
            loopVars0 = (T, P, MoFri, _SpCoi)
            # check unit
            RiLoop = 1e-3*np.array(reactionRateExe(
                loopVars0, varisSet, ratesSet))
            Ri_z[z, :] = RiLoop

            # REVIEW
            # component formation rate [kmol/m^3.s]
            ri = componentFormationRate(
                compNo, comList, reactionStochCoeff, Ri_z[z, :])

            # overall formation rate [kmol/m^3.s]
            OvR = np.sum(ri)

            # NOTE
            # enthalpy
            # heat capacity at constant pressure of mixture Cp [kJ/kmol.K] | [J/mol.K]
            # Cp mean list
            CpMeanList = calMeanHeatCapacityAtConstantPressure(comList, T)
            # print(f"Cp mean list: {CpMeanList}")
            # Cp mixture
            CpMeanMixture = calMixtureHeatCapacityAtConstantPressure(
                MoFri, CpMeanList)
            # print(f"Cp mean mixture: {CpMeanMixture}")

            # enthalpy change from Tref to T [kJ/kmol] | [J/mol]
            # enthalpy change
            EnChList = np.array(
                calEnthalpyChangeOfReaction(reactionListSorted, T))
            # heat of reaction at T [kJ/kmol] | [J/mol]
            HeReT = np.array(EnChList + StHeRe25)
            # overall heat of reaction [kJ/m^3.s]
            # exothermic reaction (negative sign)
            # endothermic sign (positive sign)
            OvHeReT = np.dot(Ri_z[z, :], HeReT)

            # NOTE
            # cooling temperature [K]
            Tm = ExHe['MeTe']
            # overall heat transfer coefficient [J/s.m2.K]
            U = ExHe['OvHeTrCo']
            # heat transfer area over volume [m2/m3]
            a = ExHe['EfHeTrAr']
            # heat transfer parameter [W/m^3.K] | [J/s.m^3.K]
            Ua = U*a
            # external heat [kJ/m^3.s]
            Qm = rmtUtil.calHeatExchangeBetweenReactorMedium(
                Tm, T, U, a, 'kJ/m^3.s')

            # NOTE
            # diff/dt
            # dxdt = []
            # matrix
            # dxdtMat = np.zeros((varNo, zNo))

            # loop vars
            const_F1 = 1/BeVoFr
            const_T1 = MoFl*CpMeanMixture
            const_T2 = 1/(CoSp*CpMeanMixture*BeVoFr + (1-BeVoFr)*CaDe*CaSpHeCa)

            # NOTE
            # concentration [mol/m^3]
            for i in range(compNo):
                # mass balance (forward difference)
                # concentration [kmol/m^3]
                # central
                Ci_c = SpCoi_z[i][z]
                # check BC
                if z == 0:
                    # BC1
                    Ci_b = SpCoi0[i]
                else:
                    # interior nodes
                    Ci_b = max(SpCoi_z[i][z - 1], CONST.EPS_CONST)
                # backward difference
                dCdz = (Ci_c - Ci_b)/dz
                # mass balance
                dxdt_F = const_F1*(-SuGaVe*dCdz + ri[i])
                dxdtMat[i][z] = dxdt_F

            # energy balance (temperature) [K]
            # temp [K]
            T_c = T_z[z]
            # check BC
            if z == 0:
                # BC1
                T_b = T0
            else:
                # interior nodes
                T_b = T_z[z - 1]
            # backward difference
            dTdz = (T_c - T_b)/dz

            dxdt_T = const_T2*(-const_T1*dTdz + (-OvHeReT + Qm))
            dxdtMat[indexT][z] = dxdt_T

        # flat
        dxdt = dxdtMat.flatten().tolist()

        print("time: ", t)
        return dxdt

# NOTE
# steady-state homogenous modeling

    def runM3(self):
        """
        M3 modeling case
        steady-state modeling
            not exactly plug-flow as dv/dz = 0
        unknowns: Ci, T, P
            velocity is calculated from EOS consiering feed Tf, Pf, Cf
        """
        # NOTE
        # start computation
        start = timer()

        # solver setting
        solverConfig = self.modelInput['solver-config']
        solverIVPSet = solverConfig['ivp']

        # model info
        modelId = self.modelInput['model']
        # operating conditions
        P = self.modelInput['operating-conditions']['pressure']
        T = self.modelInput['operating-conditions']['temperature']

        # reaction list
        reactionDict = self.modelInput['reactions']
        reactionList = rmtUtil.buildReactionList(reactionDict)
        # reaction rate expression
        reactionRateExpr = self.modelInput['reaction-rates']

        # component list
        compList = self.modelInput['feed']['components']['shell']

        # graph label setting
        labelList = compList.copy()
        labelList.append("Temperature")
        labelList.append("Pressure")

        # component no
        compNo = len(compList)
        indexTemp = compNo
        indexPressure = indexTemp + 1

        # reactor spec
        ReSpec = self.modelInput['reactor']
        # reactor inner diameter [m]
        ReInDi = ReSpec['ReInDi']
        # reactor length [m]
        ReLe = ReSpec['ReLe']
        # cross-sectional area [m^2]
        CrSeAr = CONST.PI_CONST*(ReInDi ** 2)/4
        # particle diameter [m]
        PaDi = ReSpec['PaDi']

        ## inlet values ##
        # inlet volumetric flowrate at T,P [m^3/s]
        VoFlRa0 = self.modelInput['feed']['volumetric-flowrate']
        # REVIEW
        # inlet species concentration [mol/m^3]
        SpCoi0 = 1*np.array(self.modelInput['feed']['concentration'])
        # inlet total concentration [mol/m^3]
        SpCo0 = np.sum(SpCoi0)

        # component molecular weight [g/mol]
        MoWei = rmtUtil.extractCompData(self.internalData, "MW")

        # external heat
        ExHe = self.modelInput['external-heat']

        # gas mixture viscosity [Pa.s]
        GaMiVi = self.modelInput['feed']['mixture-viscosity']

        # var no (Ci,T,P)
        varNo = compNo + 2

        # initial values
        IV = np.zeros(varNo)
        IV[0:compNo] = SpCoi0
        IV[indexTemp] = T
        IV[indexPressure] = P
        # print(f"IV: {IV}")

        # parameters
        # component data
        reactionListSorted = self.reactionListSorted
        # reaction coefficient
        reactionStochCoeff = self.reactionStochCoeffList

        # standard heat of reaction at 25C [kJ/kmol]
        StHeRe25 = np.array(
            list(map(calStandardEnthalpyOfReaction, reactionList)))

        # fun parameters
        FunParam = {
            "compList": compList,
            "const": {
                "CrSeAr": CrSeAr,
                "MoWei": MoWei,
                "StHeRe25": StHeRe25,
                "GaMiVi": GaMiVi
            },
            "ReSpec": ReSpec,
            "ExHe": ExHe,
            "constBC1": {
                "VoFlRa0": VoFlRa0,
                "SpCoi0": SpCoi0,
                "SpCo0": SpCo0,
                "P0": P,
                "T0": T
            },
            "reactionRateExpr": reactionRateExpr,
        }

        # save data
        # timesNo = solverSetting['S3']['timesNo']
        timesNo = solverSetting['M9']['zNo']

        # time span
        # t = (0.0, rea_L)
        t = np.array([0, ReLe])
        t_span = np.array([0, ReLe])
        times = np.linspace(t_span[0], t_span[1], timesNo)
        # tSpan = np.linspace(0, rea_L, 25)

        # solver selection
        # BDF, Radau, LSODA
        solverIVP = "LSODA" if solverIVPSet == 'default' else solverIVPSet

        # ode call
        sol = solve_ivp(PackedBedHomoReactorClass.modelEquationM3,
                        t, IV, method=solverIVP, t_eval=times, args=(reactionListSorted, reactionStochCoeff, FunParam))

        # ode result
        successStatus = sol.success
        dataX = sol.t
        # all results
        dataYs = sol.y
        # concentration [mol/m^3]
        dataYs1 = sol.y[0:compNo, :]
        labelListYs1 = labelList[0:compNo]
        # REVIEW
        # convert molar flowrate to mole fraction
        # convert concentration to mole fraction
        dataYs1_Ctot = np.sum(dataYs1, axis=0)
        dataYs1_MoFri = dataYs1/dataYs1_Ctot
        # temperature
        dataYs2 = sol.y[indexTemp, :]
        labelListYs3 = labelList[indexTemp]
        # pressure
        dataYs3 = sol.y[indexPressure, :]

        # FIXME
        # build matrix
        _dataYs = np.concatenate(
            (dataYs1_MoFri, [dataYs2]), axis=0)

        # NOTE
        # end of computation
        end = timer()
        elapsed = roundNum(end - start)

        # plot info
        plotTitle = f"Steady-State Modeling {modelId} with timesNo: {timesNo} within {elapsed}"

        # check
        if successStatus is True:
            # plot setting: build (x,y) series
            XYList = pltc.plots2DSetXYList(dataX, _dataYs)
            # -> add label
            dataList = pltc.plots2DSetDataList(XYList, labelList)
            # datalists
            dataLists = [dataList[0:compNo],
                         dataList[indexTemp]]
            # select datalist
            _dataListsSelected = selectFromListByIndex([0, -1], dataLists)
            # subplot result
            pltc.plots2DSub(_dataListsSelected, "Reactor Length (m)",
                            "Concentration (mol/m^3)", plotTitle)

            # plot result
            # pltc.plots2D(dataList[0:compNo], "Reactor Length (m)",
            #              "Concentration (mol/m^3)", "1D Plug-Flow Reactor")

            # pltc.plots2D(dataList[indexFlux], "Reactor Length (m)",
            #              "Flux (kmol/m^2.s)", "1D Plug-Flow Reactor")

            # pltc.plots2D(dataList[indexTemp], "Reactor Length (m)",
            #              "Temperature (K)", "1D Plug-Flow Reactor")

        else:
            _dataYs = []
            XYList = []
            dataList = []

        # return
        res = {
            "dataYs": _dataYs,
            "XYList": XYList,
            "dataList": dataList
        }

        return res

    def modelEquationM3(t, y, reactionListSorted, reactionStochCoeff, FunParam):
        """
        M3 model
        mass, energy, and momentum balance equations
        modelParameters:
            reactionListSorted: reactant/product and coefficient lists
            reactionStochCoeff: reaction stoichiometric coefficient
            FunParam:
                compList: component list
                const
                    CrSeAr: reactor cross sectional area [m^2]
                    MoWei: component molecular weight [g/mol]
                    StHeRe25: standard heat of reaction at 25C [kJ/kmol] | [J/mol]
                    GaMiVi: gas mixture viscosity [Pa.s]
                ReSpec: reactor spec
                ExHe: exchange heat spec
                    OvHeTrCo: overall heat transfer coefficient [J/m^2.s.K]
                    EfHeTrAr: effective heat transfer area [m^2]
                    MeTe: medium temperature [K]
            reactionRateExpr: reaction rate expressions
        """
        # fun params
        # component symbol list
        comList = FunParam['compList']
        # const ->
        const = FunParam['const']
        # cross-sectional area [m^2]
        CrSeAr = const['CrSeAr']
        # component molecular weight [g/mol]
        MoWei = const['MoWei']
        # standard heat of reaction at 25C [kJ/kmol] | [J/mol]
        StHeRe25 = const['StHeRe25']
        # gas viscosity [Pa.s]
        GaMiVi = const['GaMiVi']
        # reactor spec ->
        ReSpec = FunParam['ReSpec']
        # bed void fraction - porosity
        BeVoFr = ReSpec['BeVoFr']
        # bulk density (catalyst bed density)
        CaBeDe = ReSpec['CaBeDe']
        # particle diameter [m]
        PaDi = ReSpec['PaDi']
        # exchange heat spec ->
        ExHe = FunParam['ExHe']

        # boundary conditions constants
        constBC1 = FunParam['constBC1']
        ## inlet values ##
        # inlet volumetric flowrate at T,P [m^3/s]
        VoFlRa0 = constBC1['VoFlRa0']
        # inlet species concentration [mol/m^3]
        SpCoi0 = constBC1['SpCoi0']
        # inlet total concentration [mol/m^3]
        SpCo0 = constBC1['SpCo0']
        # inlet pressure [Pa]
        P0 = constBC1['P0']
        # inlet temperature [K]
        T0 = constBC1['T0']

        # reaction rate expressions
        reactionRateExpr = FunParam['reactionRateExpr']
        # using equation
        varisSet = reactionRateExpr['VARS']
        ratesSet = reactionRateExpr['RATES']

        # calculate
        # molar flowrate [kmol/s]
        MoFlRa0 = SpCo0*VoFlRa0
        # superficial gas velocity [m/s]
        InGaVe0 = VoFlRa0/(CrSeAr*BeVoFr)
        # interstitial gas velocity [m/s]
        SuGaVe0 = InGaVe0*BeVoFr

        # components no
        # y: component molar flowrate, total molar flux, temperature, pressure
        compNo = len(comList)
        indexT = compNo
        indexP = indexT + 1

        # concentration species [mol/m^3]
        CoSpi = y[0:compNo]
        # temperature [K]
        T = y[indexT]
        # pressure [Pa]
        P = y[indexP]

        # total concentration [mol/m^3]
        CoSp = np.sum(CoSpi)

        # mole fraction
        MoFri = np.array(
            rmtUtil.moleFractionFromConcentrationSpecies(CoSpi))

        # gas velocity based on interstitial velocity [m/s]
        InGaVe = rmtUtil.calGaVeFromEOS(InGaVe0, SpCo0, CoSp, P0, P)
        # superficial gas velocity [m/s]
        SuGaVe = InGaVe*BeVoFr

        # total flowrate [mol/s]
        # [mol/m^3]*[m/s]*[m^2]
        MoFlRa = CoSp*SuGaVe*CrSeAr
        # molar flowrate list [mol/s]
        MoFlRai = MoFlRa*MoFri

        # FIXME
        # molar flux [mol/m^2.s]
        MoFl = MoFlRa/CrSeAr

        # volumetric flowrate [m^3/s]
        VoFlRai = calVolumetricFlowrateIG(P, T, MoFlRai)

        # mixture molecular weight [kg/mol]
        MiMoWe = rmtUtil.mixtureMolecularWeight(MoFri, MoWei, "kg/mol")

        # gas density [kg/m^3]
        GaDe = calDensityIG(MiMoWe, CoSp)
        GaDeEOS = calDensityIGFromEOS(P, T, MiMoWe)

        # NOTE
        # momentum equation
        # REVIEW
        # ergun equation
        ergA = 150*GaMiVi*SuGaVe/(PaDi**2)
        ergB = ((1-BeVoFr)**2)/(BeVoFr**3)
        ergC = 1.75*GaDe*(SuGaVe**2)/PaDi
        ergD = (1-BeVoFr)/(BeVoFr**3)
        RHS_ergun = -1*(ergA*ergB + ergC*ergD)

        # NOTE
        # kinetics
        # component formation rate [mol/m^3.s]
        # conversion
        # FIXME
        # Ri = 1000*np.array(PackedBedReactorClass.modelReactions(
        #     P, T, MoFri, CaBeDe))
        # loop
        loopVars0 = (T, P, MoFri, CoSpi)
        # check unit
        r0 = np.array(reactionRateExe(
            loopVars0, varisSet, ratesSet))

        # loop
        Ri = r0

        # component formation rate [mol/m^3.s]
        # rf[mol/kgcat.s]*CaBeDe[kgcat/m^3]
        # call [mol/m^3.s]
        ri = componentFormationRate(
            compNo, comList, reactionStochCoeff, Ri)

        # overall formation rate [mol/m^3.s]
        OvR = np.sum(ri)

        # enthalpy
        # heat capacity at constant pressure of mixture Cp [kJ/kmol.K] | [J/mol.K]
        # Cp mean list
        CpMeanList = calMeanHeatCapacityAtConstantPressure(comList, T)
        # print(f"Cp mean list: {CpMeanList}")
        # Cp mixture
        CpMeanMixture = calMixtureHeatCapacityAtConstantPressure(
            MoFri, CpMeanList)
        # print(f"Cp mean mixture: {CpMeanMixture}")

        # enthalpy change from Tref to T [kJ/kmol] | [J/mol]
        # enthalpy change
        EnChList = np.array(calEnthalpyChangeOfReaction(reactionListSorted, T))
        # heat of reaction at T [kJ/kmol] | [J/mol]
        HeReT = np.array(EnChList + StHeRe25)
        # overall heat of reaction [J/m^3.s]
        OvHeReT = np.dot(Ri, HeReT)

        # NOTE
        #
        # cooling temperature [K]
        Tm = ExHe['MeTe']
        # overall heat transfer coefficient [J/s.m2.K]
        U = ExHe['OvHeTrCo']
        # heat transfer area over volume [m2/m3]
        a = ExHe['EfHeTrAr']
        # heat transfer parameter [W/m^3.K] | [J/s.m^3.K]
        Ua = U*a
        # external heat [J/m^3.s]
        Qm = Ua*(Tm - T)

        # NOTE
        # diff/dt
        dxdt = []
        # loop vars
        const_C1 = 1/SuGaVe
        const_T1 = 1/(MoFl*CpMeanMixture)

        # mass balance (concentration) [mol/m^3]
        for i in range(compNo):
            dxdt_Ci = const_C1*ri[i]
            dxdt.append(dxdt_Ci)

        # energy balance (temperature) [K]
        dxdt_T = const_T1*(-OvHeReT + Qm)
        dxdt.append(dxdt_T)

        # momentum balance (ergun equation)
        dxdt_P = RHS_ergun
        dxdt.append(dxdt_P)

        return dxdt

# NOTE
# steady-state homogenous modeling

    def runM4(self):
        """
        M4 modeling case
        steady-state modeling
        unknowns: Ci,P,T,v
            CT, GaDe, are calculated from EOS
        """
        # operating conditions
        P = self.modelInput['operating-conditions']['pressure']
        T = self.modelInput['operating-conditions']['temperature']

        # reaction list
        reactionDict = self.modelInput['reactions']
        reactionList = rmtUtil.buildReactionList(reactionDict)

        # component list
        compList = self.modelInput['feed']['components']['shell']

        # graph label setting
        labelList = compList.copy()
        labelList.append("Temperature")
        labelList.append("Pressure")
        labelList.append("Velocity")

        # component no
        compNo = len(compList)
        indexTemp = compNo
        indexPressure = indexTemp + 1
        indexVelocity = indexPressure + 1
        indexDensity = indexVelocity + 1

        # reactor spec
        ReSpec = self.modelInput['reactor']
        # reactor inner diameter [m]
        ReInDi = ReSpec['ReInDi']
        # reactor length [m]
        ReLe = ReSpec['ReLe']
        # cross-sectional area [m^2]
        CrSeAr = CONST.PI_CONST*(ReInDi ** 2)/4
        # particle diameter [m]
        PaDi = ReSpec['PaDi']

        ## inlet values ##
        # inlet volumetric flowrate at T,P [m^3/s]
        VoFlRa0 = self.modelInput['feed']['volumetric-flowrate']
        # inlet species concentration [mol/m^3]
        SpCoi0 = np.array(self.modelInput['feed']['concentration'])
        # inlet total concentration [mol/m^3]
        SpCo0 = np.sum(SpCoi0)
        # inlet superficial velocity [m/s]
        SuGaVe0 = self.modelInput['feed']['superficial-velocity']

        # mole fraction
        MoFri = np.array(
            rmtUtil.moleFractionFromConcentrationSpecies(SpCoi0))

        # component molecular weight [g/mol]
        MoWei = rmtUtil.extractCompData(self.internalData, "MW")

        # external heat
        ExHe = self.modelInput['external-heat']

        # gas mixture viscosity [Pa.s]
        GaMiVi = self.modelInput['feed']['mixture-viscosity']

        # reaction rate expression
        reactionRateExpr = self.modelInput['reaction-rates']

        # mixture molecular weight [kg/mol]
        MiMoWe = rmtUtil.mixtureMolecularWeight(MoFri, MoWei, "kg/mol")

        # inlet density [kg/m^3]
        GaDe0 = MiMoWe*SpCo0

        # var no Ci,T,P,v)
        varNo = compNo + 3

        # initial values
        IV = np.zeros(varNo)
        IV[0:compNo] = SpCoi0
        IV[indexTemp] = T
        IV[indexPressure] = P
        IV[indexVelocity] = SuGaVe0
        # print(f"IV: {IV}")

        # parameters
        # component data
        reactionListSorted = self.reactionListSorted
        # reaction coefficient
        reactionStochCoeff = self.reactionStochCoeffList

        # standard heat of reaction at 25C [kJ/kmol]
        StHeRe25 = np.array(
            list(map(calStandardEnthalpyOfReaction, reactionList)))

        # fun parameters
        FunParam = {
            "compList": compList,
            "const": {
                "CrSeAr": CrSeAr,
                "MoWei": MoWei,
                "StHeRe25": StHeRe25,
                "GaMiVi": GaMiVi
            },
            "ReSpec": ReSpec,
            "ExHe": ExHe,
            "constBC1": {
                "VoFlRa0": VoFlRa0,
                "SpCoi0": SpCoi0,
                "SpCo0": SpCo0,
                "P0": P,
                "T0": T
            },
            "reactionRateExpr": reactionRateExpr
        }

        # save data
        timesNo = solverSetting['S3']['timesNo']

        # time span
        # t = (0.0, rea_L)
        t = np.array([0, ReLe])
        t_span = np.array([0, ReLe])
        times = np.linspace(t_span[0], t_span[1], timesNo)
        # tSpan = np.linspace(0, rea_L, 25)

        # ode call
        sol = solve_ivp(PackedBedHomoReactorClass.modelEquationM4,
                        t, IV, method="LSODA", t_eval=times, args=(reactionListSorted, reactionStochCoeff, FunParam))

        # ode result
        successStatus = sol.success
        dataX = sol.t
        # all results
        dataYs = sol.y
        # concentration [mol/m^3]
        dataYs1 = sol.y[0:compNo, :]
        labelListYs1 = labelList[0:compNo]
        # REVIEW
        # convert concentration to mole fraction
        dataYs1_Ctot = np.sum(dataYs1, axis=0)
        dataYs1_MoFri = dataYs1/dataYs1_Ctot
        # temperature [K]
        dataYs2 = sol.y[indexTemp, :]
        labelListYs3 = labelList[indexTemp]
        # pressure [Pa]
        dataYs3 = sol.y[indexPressure, :]
        # velocity [m/s]
        dataYs4 = sol.y[indexVelocity, :]

        # FIXME
        # build matrix
        _dataYs = np.concatenate(
            (dataYs1_MoFri, [dataYs2]), axis=0)
        _dataYsPlot = np.concatenate(
            (dataYs1_MoFri, [dataYs2], [dataYs3], [dataYs4]), axis=0)

        # plot info
        plotTitle = f"Steady-State Modeling [M4] with timesNo: {timesNo}"

        # NOTE
        # # steady-state result
        # # txt
        # # ssModelingResult = np.loadtxt('ssModeling.txt', dtype=np.float64)
        # # binary
        # ssModelingResult = np.load('ResM1.npy')
        # # ssdataXs = np.linspace(0, ReLe, zNo)
        # ssXYList = pltc.plots2DSetXYList(dataX, ssModelingResult)
        # ssdataList = pltc.plots2DSetDataList(ssXYList, labelList)
        # # datalists
        # ssdataLists = [ssdataList[0:compNo],
        #                ssdataList[indexTemp]]

        # check
        if successStatus is True:
            # plot setting: build (x,y) series
            XYList = pltc.plots2DSetXYList(dataX, _dataYsPlot)
            # -> add label
            dataList = pltc.plots2DSetDataList(XYList, labelList)
            # datalists
            dataLists = [dataList[0:compNo],
                         dataList[indexTemp], dataList[indexPressure], dataList[indexVelocity]]
            # select datalist
            _dataListsSelected = selectFromListByIndex([0, -3], dataLists)
            # subplot result
            pltc.plots2DSub(_dataListsSelected, "Reactor Length (m)",
                            "Concentration (mol/m^3)", plotTitle)

        else:
            _dataYs = []
            XYList = []
            dataList = []

        # return
        res = {
            "dataYs": _dataYs,
            "XYList": XYList,
            "dataList": dataList
        }

        return res

    def modelEquationM4(t, y, reactionListSorted, reactionStochCoeff, FunParam):
        """
            M4 model
            mass, energy, and momentum balance equations
            modelParameters:
                reactionListSorted: reactant/product and coefficient lists
                reactionStochCoeff: reaction stoichiometric coefficient
                FunParam:
                    compList: component list
                    const
                        CrSeAr: reactor cross sectional area [m^2]
                        MoWei: component molecular weight [g/mol]
                        StHeRe25: standard heat of reaction at 25C [kJ/kmol] | [J/mol]
                        GaMiVi: gas mixture viscosity [Pa.s]
                    ReSpec: reactor spec
                    ExHe: exchange heat spec
                        OvHeTrCo: overall heat transfer coefficient [J/m^2.s.K]
                        EfHeTrAr: effective heat transfer area [m^2]
                        MeTe: medium temperature [K]

        """
        # fun params
        # component symbol list
        comList = FunParam['compList']
        # const ->
        const = FunParam['const']
        # cross-sectional area [m^2]
        CrSeAr = const['CrSeAr']
        # component molecular weight [g/mol]
        MoWei = const['MoWei']
        # standard heat of reaction at 25C [kJ/kmol] | [J/mol]
        StHeRe25 = const['StHeRe25']
        # gas viscosity [Pa.s]
        GaMiVi = const['GaMiVi']
        # reactor spec ->
        ReSpec = FunParam['ReSpec']
        # bed void fraction - porosity
        BeVoFr = ReSpec['BeVoFr']
        # bulk density (catalyst bed density)
        CaBeDe = ReSpec['CaBeDe']
        # particle diameter [m]
        PaDi = ReSpec['PaDi']
        # exchange heat spec ->
        ExHe = FunParam['ExHe']

        # boundary conditions constants
        constBC1 = FunParam['constBC1']
        ## inlet values ##
        # inlet volumetric flowrate at T,P [m^3/s]
        VoFlRa0 = constBC1['VoFlRa0']
        # inlet species concentration [kmol/m^3]
        SpCoi0 = constBC1['SpCoi0']
        # inlet total concentration [kmol/m^3]
        SpCo0 = constBC1['SpCo0']
        # inlet pressure [Pa]
        P0 = constBC1['P0']
        # inlet temperature [K]
        T0 = constBC1['T0']

        # reaction rate expressions
        reactionRateExpr = FunParam['reactionRateExpr']
        # using equation
        varisSet = reactionRateExpr['VARS']
        ratesSet = reactionRateExpr['RATES']

        # calculate
        # molar flowrate [kmol/s]
        MoFlRa0 = SpCo0*VoFlRa0
        # superficial gas velocity [m/s]
        InGaVe0 = VoFlRa0/(CrSeAr*BeVoFr)
        # interstitial gas velocity [m/s]
        SuGaVe0 = InGaVe0*BeVoFr

        # components no
        # y: component molar flowrate, total molar flux, temperature, pressure
        compNo = len(comList)
        indexT = compNo
        indexP = indexT + 1
        indexVelocity = indexP + 1

        # concentration species [mol/m^3]
        CoSpi = y[0:compNo]
        # temperature [K]
        T = y[indexT]
        # pressure [Pa]
        P = y[indexP]
        # velocity
        SuGaVe = y[indexVelocity]

        # total concentration [mol/m^3]
        CoSp = np.sum(CoSpi)

        # mole fraction
        MoFri = np.array(
            rmtUtil.moleFractionFromConcentrationSpecies(CoSpi))

        # gas velocity based on interstitial velocity [m/s]
        # InGaVe = rmtUtil.calGaVeFromEOS(InGaVe0, SpCo0, CoSp, P0, P)
        # superficial gas velocity [m/s]
        # SuGaVe = InGaVe*BeVoFr

        # total flowrate [mol/s]
        # [mol/m^3]*[m/s]*[m^2]
        MoFlRa = CoSp*SuGaVe*CrSeAr
        # molar flowrate list [mol/s]
        MoFlRai = MoFlRa*MoFri

        # molar flux [mol/m^2.s]
        MoFl = MoFlRa/CrSeAr

        # volumetric flowrate [m^3/s]
        VoFlRai = calVolumetricFlowrateIG(P, T, MoFlRai)

        # mixture molecular weight [kg/mol]
        MiMoWe = rmtUtil.mixtureMolecularWeight(MoFri, MoWei, "kg/mol")

        # gas density [kg/m^3]
        GaDe = calDensityIG(MiMoWe, CoSp)
        # GaDeEOS = calDensityIGFromEOS(P, T, MiMoWe)

        # NOTE
        # momentum equation
        # REVIEW
        # ergun equation
        ergA = 150*GaMiVi*SuGaVe/(PaDi**2)
        ergB = ((1-BeVoFr)**2)/(BeVoFr**3)
        ergC = 1.75*GaDe*(SuGaVe**2)/PaDi
        ergD = (1-BeVoFr)/(BeVoFr**3)
        RHS_ergun = -1*(ergA*ergB + ergC*ergD)

        # NOTE
        # kinetics
        # component formation rate [mol/m^3.s]
        # conversion
        # FIXME
        # Ri = 1000*np.array(PackedBedHomoReactorClass.modelReactions(
        #     P, T, MoFri, CaBeDe))

        # loop
        loopVars0 = (T, P, MoFri, CoSpi)
        # check unit
        r0 = np.array(reactionRateExe(
            loopVars0, varisSet, ratesSet))

        # loop
        Ri = r0

        # component formation rate [mol/m^3.s]
        # rf[mol/kgcat.s]*CaBeDe[kgcat/m^3]
        ri = np.zeros(compNo)
        for k in range(compNo):
            # reset
            _riLoop = 0
            for m in range(len(reactionStochCoeff)):
                for n in range(len(reactionStochCoeff[m])):
                    if comList[k] == reactionStochCoeff[m][n][0]:
                        _riLoop += reactionStochCoeff[m][n][1]*Ri[m]
                ri[k] = _riLoop

        # overall formation rate [mol/m^3.s]
        OvR = np.sum(ri)

        # enthalpy
        # heat capacity at constant pressure of mixture Cp [kJ/kmol.K] | [J/mol.K]
        # Cp mean list
        CpMeanList = calMeanHeatCapacityAtConstantPressure(comList, T)
        # print(f"Cp mean list: {CpMeanList}")
        # Cp mixture
        CpMeanMixture = calMixtureHeatCapacityAtConstantPressure(
            MoFri, CpMeanList)
        # print(f"Cp mean mixture: {CpMeanMixture}")

        # enthalpy change from Tref to T [kJ/kmol] | [J/mol]
        # enthalpy change
        EnChList = np.array(calEnthalpyChangeOfReaction(reactionListSorted, T))
        # heat of reaction at T [kJ/kmol] | [J/mol]
        HeReT = np.array(EnChList + StHeRe25)
        # overall heat of reaction [J/m^3.s]
        OvHeReT = np.dot(Ri, HeReT)

        # NOTE
        #
        # cooling temperature [K]
        Tm = ExHe['MeTe']
        # overall heat transfer coefficient [J/s.m2.K]
        U = ExHe['OvHeTrCo']
        # heat transfer area over volume [m2/m3]
        a = ExHe['EfHeTrAr']
        # heat transfer parameter [W/m^3.K] | [J/s.m^3.K]
        Ua = U*a
        # external heat [J/m^3.s]
        Qm = Ua*(Tm - T)

        # REVIEW
        # subs df/dt

        # NOTE
        # diff/dt
        dxdt = []
        # loop vars
        const_C1 = 1/SuGaVe
        const_T1 = 1/(MoFl*CpMeanMixture)
        const_V1 = 1/CoSp

        # RHS of ODE
        # energy balance
        dxdt_T = const_T1*(-OvHeReT + Qm)
        # momentum balance (ergun eq.)
        dxdt_P = RHS_ergun
        # velocity from global concentration
        dxdt_v = const_V1*((-SuGaVe/CONST.R_CONST) *
                           ((1/T)*dxdt_P - (P/T**2)*dxdt_T) + OvR)

        # mass balance (concentration) [mol/m^3]
        for i in range(compNo):
            dxdt_Ci = const_C1*(-CoSpi[i]*dxdt_v + ri[i])
            dxdt.append(dxdt_Ci)

        # energy balance (temperature) [K]
        # dxdt_T = const_T1*(-OvHeReT + Qm)
        dxdt.append(dxdt_T)

        # momentum balance (ergun equation)
        # dxdt_P = RHS_ergun
        dxdt.append(dxdt_P)

        # velocity [m/s]
        dxdt.append(dxdt_v)

        return dxdt

# NOTE
# dynamic homogenous modeling

    def runM5(self):
        """
        M5 modeling case
        dynamic model
        unknowns: Ci, T (dynamic), P, v (static)
            CT, GaDe = f(P, T, n)
        """
        # start computation
        start = timer()

        # solver setting
        solverConfig = self.modelInput['solver-config']
        solverIVPSet = solverConfig['ivp']

        # operating conditions
        P = self.modelInput['operating-conditions']['pressure']
        T = self.modelInput['operating-conditions']['temperature']
        # operation time [s]
        opT = self.modelInput['operating-conditions']['period']

        # reaction list
        reactionDict = self.modelInput['reactions']
        reactionList = rmtUtil.buildReactionList(reactionDict)
        # number of reactions
        reactionListNo = len(reactionList)

        # component list
        compList = self.modelInput['feed']['components']['shell']

        # graph label setting
        labelList = compList.copy()
        labelList.append("Temperature")
        # labelList.append("Pressure")

        # component no
        compNo = len(compList)
        indexTemp = compNo
        indexPressure = indexTemp + 1
        indexVelocity = indexPressure + 1

        # reactor spec
        ReSpec = self.modelInput['reactor']
        # reactor inner diameter [m]
        ReInDi = ReSpec['ReInDi']
        # reactor length [m]
        ReLe = ReSpec['ReLe']
        # cross-sectional area [m^2]
        CrSeAr = CONST.PI_CONST*(ReInDi ** 2)/4
        # particle diameter [m]
        PaDi = ReSpec['PaDi']
        # bed void fraction - porosity
        BeVoFr = ReSpec['BeVoFr']

        ## inlet values ##
        # inlet volumetric flowrate at T,P [m^3/s]
        VoFlRa0 = self.modelInput['feed']['volumetric-flowrate']
        # inlet species concentration [kmol/m^3]
        SpCoi0 = np.array(self.modelInput['feed']['concentration'])
        # inlet total concentration [kmol/m^3]
        SpCo0 = np.sum(SpCoi0)
        # inlet superficial velocity [m/s]
        SuGaVe0 = self.modelInput['feed']['superficial-velocity']

        # reaction rate expression
        reactionRateExpr = self.modelInput['reaction-rates']

        # component molecular weight [g/mol]
        MoWei = rmtUtil.extractCompData(self.internalData, "MW")

        # external heat
        ExHe = self.modelInput['external-heat']
        # cooling temperature [K]
        Tm = ExHe['MeTe']
        # overall heat transfer coefficient [J/s.m2.K]
        U = ExHe['OvHeTrCo']
        # heat transfer area over volume [m2/m3]
        a = 4/ReInDi  # ExHe['EfHeTrAr']

        # gas mixture viscosity [Pa.s]
        GaMiVi = self.modelInput['feed']['mixture-viscosity']

        # finite difference points in the z direction
        zNo = solverSetting['S2']['zNo']
        # length list
        dataXs = np.linspace(0, ReLe, zNo)
        # element size - dz [m]
        dz = ReLe/(zNo-1)

        # var no (Ci,T)
        varNo = compNo + 1
        # concentration var no
        varNoCon = compNo*zNo
        # temperature var no
        varNoTemp = 1*zNo
        # total var no along the reactor length
        varNoT = varNo*zNo

        # initial values at t = 0 and z >> 0
        IVMatrixShape = (varNo, zNo)
        IV2D = np.zeros(IVMatrixShape)
        # initialize IV2D
        # -> concentration [kmol/m^3]
        for i in range(compNo):
            for j in range(zNo):
                IV2D[i][j] = SpCoi0[i]

        for j in range(zNo):
            IV2D[indexTemp][j] = T

        # flatten IV
        IV = IV2D.flatten()

        # print(f"IV: {IV}")

        # parameters
        # component data
        reactionListSorted = self.reactionListSorted
        # reaction coefficient
        reactionStochCoeff = self.reactionStochCoeffList

        # standard heat of reaction at 25C [kJ/kmol]
        StHeRe25 = np.array(
            list(map(calStandardEnthalpyOfReaction, reactionList)))

        # fun parameters
        FunParam = {
            "compList": compList,
            "const": {
                "CrSeAr": CrSeAr,
                "MoWei": MoWei,
                "StHeRe25": StHeRe25,
                "GaMiVi": GaMiVi,
                "zNo": zNo,
                "varNo": varNo,
                "varNoT": varNoT,
                "reactionListNo": reactionListNo,
                "dz": dz
            },
            "ReSpec": ReSpec,
            "ExHe":  {
                "OvHeTrCo": U,
                "EfHeTrAr": a,
                "MeTe": Tm
            },
            "constBC1": {
                "VoFlRa0": VoFlRa0,
                "SpCoi0": SpCoi0,
                "SpCo0": SpCo0,
                "P0": P,
                "T0": T,
                "SuGaVe0": SuGaVe0
            },
            "reactionRateExpr": reactionRateExpr
        }

        # time span
        tNo = solverSetting['S2']['tNo']
        opTSpan = np.linspace(0, opT, tNo + 1)

        # save data
        timesNo = solverSetting['S2']['timesNo']

        # result
        dataPack = []

        # build data list
        # over time
        dataPacktime = np.zeros((varNo, tNo, zNo))
        #

        # solver selection
        # BDF, Radau, LSODA
        solverIVP = "LSODA" if solverIVPSet == 'default' else solverIVPSet

        # time loop
        for i in range(tNo):
            # set time span
            t = np.array([opTSpan[i], opTSpan[i+1]])
            times = np.linspace(t[0], t[1], timesNo)
            print(f"time: {t} seconds")

            # ode call
            sol = solve_ivp(PackedBedHomoReactorClass.modelEquationM5,
                            t, IV, method=solverIVP, t_eval=times, args=(reactionListSorted, reactionStochCoeff, FunParam))

            # ode result
            successStatus = sol.success
            # check
            if successStatus is False:
                raise

            # time interval
            dataTime = sol.t
            # all results
            dataYs = sol.y

            # component concentration [kmol/m^3]
            dataYs1 = dataYs[0:varNoCon, -1]
            # 2d matrix
            dataYs1_Reshaped = np.reshape(dataYs1, (compNo, zNo))
            # REVIEW
            # convert concentration to mole fraction
            dataYs1_Ctot = np.sum(dataYs1_Reshaped, axis=0)
            dataYs1_MoFri = dataYs1_Reshaped/dataYs1_Ctot
            # temperature - 2d matrix
            dataYs2 = np.array([dataYs[varNoCon:varNoT, -1]])

            # combine
            _dataYs = np.concatenate((dataYs1_MoFri, dataYs2), axis=0)

            # save data
            dataPack.append({
                "successStatus": successStatus,
                "dataTime": dataTime[-1],
                "dataYCons": dataYs1_Reshaped,
                "dataYTemp": dataYs2,
                "dataYs": _dataYs
            })

            for m in range(varNo):
                # var list
                dataPacktime[m][i, :] = dataPack[i]['dataYs'][m, :]

            # update initial values [IV]
            IV = dataYs[:, -1]

        # NOTE
        # end of computation
        end = timer()
        elapsed = roundNum(end - start)

        # NOTE
        # steady-state result
        # txt
        # ssModelingResult = np.loadtxt('ssModeling.txt', dtype=np.float64)
        # binary
        # ssModelingResult = np.load('ResM1.npy')
        # ssdataXs = np.linspace(0, ReLe, zNo)
        # ssXYList = pltc.plots2DSetXYList(dataXs, ssModelingResult)
        # ssdataList = pltc.plots2DSetDataList(ssXYList, labelList)
        # datalists
        # ssdataLists = [ssdataList[0:compNo],
        #                ssdataList[indexTemp]]
        # subplot result
        # pltc.plots2DSub(ssdataLists, "Reactor Length (m)",
        #                 "Concentration (mol/m^3)", "1D Plug-Flow Reactor")

        # plot info
        plotTitle = f"Dynamic Modeling for opT: {opT} with zNo: {zNo}, tNo: {tNo} within {elapsed} seconds"

        # REVIEW
        # display result at specific time
        for i in range(tNo):
            # var list
            _dataYs = dataPack[i]['dataYs']
            # plot setting: build (x,y) series
            XYList = pltc.plots2DSetXYList(dataXs, _dataYs)
            # -> add label
            dataList = pltc.plots2DSetDataList(XYList, labelList)
            # datalists
            dataLists = [dataList[0:compNo],
                         dataList[indexTemp]]
            if i == tNo-1:
                # subplot result
                pltc.plots2DSub(dataLists, "Reactor Length (m)",
                                "Concentration (mol/m^3)", plotTitle)

        # REVIEW
        # display result within time span
        _dataListsLoop = []
        _labelNameTime = []

        for i in range(varNo):
            # var list
            _dataPacktime = dataPacktime[i]
            # plot setting: build (x,y) series
            XYList = pltc.plots2DSetXYList(dataXs, _dataPacktime)
            # -> add label
            # build label
            for t in range(tNo):
                _name = labelList[i] + " at t=" + str(opTSpan[t+1])

                _labelNameTime.append(_name)

            dataList = pltc.plots2DSetDataList(XYList, _labelNameTime)
            # datalists
            _dataListsLoop.append(dataList[0:tNo])
            # reset
            _labelNameTime = []

        # select items
        # indices = [0, 2, -1]
        # selected_elements = [_dataListsLoop[index] for index in indices]
        # select datalist
        _dataListsSelected = selectFromListByIndex([1, -1], _dataListsLoop)

        # subplot result
        # pltc.plots2DSub(_dataListsSelected, "Reactor Length (m)",
        #                 "Concentration (mol/m^3)", "Dynamic Modeling of 1D Plug-Flow Reactor")

        # return
        res = {
            "XYList": XYList,
            "dataList": dataList
        }

        return res

    def modelEquationM5(t, y, reactionListSorted, reactionStochCoeff, FunParam):
        """
            [dynamic modeling]
            mass, energy, and momentum balance equations
            modelParameters:
                reactionListSorted: reactant/product and coefficient lists
                reactionStochCoeff: reaction stoichiometric coefficient
                FunParam:
                    compList: component list
                    const
                        CrSeAr: reactor cross sectional area [m^2]
                        MoWei: component molecular weight [g/mol]
                        StHeRe25: standard heat of reaction at 25C [kJ/kmol] | [J/mol]
                        GaMiVi: gas mixture viscosity [Pa.s]
                        zNo: number of finite difference in the z direction
                        varNo: number of variables (Ci, CT, T)
                        varNoT: number of variables in the domain (zNo*varNoT)
                        reactionListNo: reaction list number
                        dz: differential length [m]
                    ReSpec: reactor spec
                    ExHe: exchange heat spec
                        OvHeTrCo: overall heat transfer coefficient [J/m^2.s.K]
                        EfHeTrAr: effective heat transfer area [m^2]
                        MeTe: medium temperature [K]
                    constBC1:
                        VoFlRa0: inlet volumetric flowrate [m^3/s],
                        SpCoi0: species concentration [kmol/m^3],
                        SpCo0: total concentration [kmol/m^3]
                        P0: inlet pressure [Pa]
                        T0: inlet temperature [K],
                    reactionRateExpr: reaction rate expressions
                        VARS: list of variable
                        RATES: list of rate expressions
        """
        # fun params
        # component symbol list
        comList = FunParam['compList']
        # const ->
        const = FunParam['const']
        # cross-sectional area [m^2]
        CrSeAr = const['CrSeAr']
        # component molecular weight [g/mol]
        MoWei = const['MoWei']
        # standard heat of reaction at 25C [kJ/kmol] | [J/mol]
        StHeRe25 = const['StHeRe25']
        # gas viscosity [Pa.s]
        GaMiVi = const['GaMiVi']
        # reaction no
        reactionListNo = const['reactionListNo']
        # dz [m]
        dz = const['dz']
        # reactor spec ->
        ReSpec = FunParam['ReSpec']
        # particle diameter [m]
        PaDi = ReSpec['PaDi']
        # bed void fraction - porosity
        BeVoFr = ReSpec['BeVoFr']
        # bulk density (catalyst bed density)
        CaBeDe = ReSpec['CaBeDe']
        # catalyst density [kgcat/m^3 of particle]
        CaDe = ReSpec['CaDe']
        # catalyst heat capacity at constant pressure [kJ/kg.K]
        CaSpHeCa = ReSpec['CaSpHeCa']

        # exchange heat spec ->
        ExHe = FunParam['ExHe']
        # zNo
        zNo = const['zNo']
        # var no.
        varNo = const['varNo']
        # var no. in the domain
        varNoT = const['varNoT']

        # boundary conditions constants
        constBC1 = FunParam['constBC1']
        ## inlet values ##
        # inlet volumetric flowrate at T,P [m^3/s]
        VoFlRa0 = constBC1['VoFlRa0']
        # inlet species concentration [kmol/m^3]
        SpCoi0 = constBC1['SpCoi0']
        # inlet total concentration [kmol/m^3]
        SpCo0 = constBC1['SpCo0']
        # inlet pressure [Pa]
        P0 = constBC1['P0']
        # inlet temperature [K]
        T0 = constBC1['T0']

        # reaction rate expressions
        reactionRateExpr = FunParam['reactionRateExpr']
        # using equation
        varisSet = reactionRateExpr['VARS']
        ratesSet = reactionRateExpr['RATES']

        # calculate
        # molar flowrate [kmol/s]
        MoFlRa0 = SpCo0*VoFlRa0
        # superficial gas velocity [m/s]
        InGaVe0 = VoFlRa0/(CrSeAr*BeVoFr)
        # interstitial gas velocity [m/s]
        SuGaVe0 = InGaVe0*BeVoFr

        # superficial gas velocity [m/s]
        InGaVeList_z = np.zeros(zNo)
        InGaVeList_z[0] = InGaVe0

        # total molar flux [kmol/m^2.s]
        MoFl_z = np.zeros(zNo)
        MoFl_z[0] = MoFlRa0

        # reaction rate
        Ri_z = np.zeros((zNo, reactionListNo))

        # pressure [Pa]
        P_z = np.zeros(zNo + 1)
        P_z[0] = P0

        # superficial gas velocity [m/s]
        v_z = np.zeros(zNo + 1)
        v_z[0] = SuGaVe0

        # components no
        # y: component molar flowrate, total molar flux, temperature, pressure
        compNo = len(comList)
        indexT = compNo
        indexP = indexT + 1
        indexV = indexP + 1

        # species concentration [kmol/m^3]
        CoSpi = np.zeros(compNo)

        # reaction rate
        ri = np.zeros(compNo)
        ri0 = np.zeros(compNo)

        # NOTE
        # distribute y[i] value through the reactor length
        # reshape
        yLoop = np.reshape(y, (varNo, zNo))

        # -> concentration [mol/m^3]
        SpCoi_z = np.zeros((compNo, zNo))
        for i in range(compNo):
            _SpCoi = yLoop[i, :]
            SpCoi_z[i, :] = _SpCoi

        # temperature [K]
        T_z = np.zeros(zNo)
        T_z = yLoop[indexT, :]

        # diff/dt
        # dxdt = []
        # matrix
        dxdtMat = np.zeros((varNo, zNo))

        # NOTE
        # FIXME
        # define ode equations for each finite difference [zNo]
        for z in range(zNo):
            ## block ##

            # FIXME
            # concentration species [kmol/m^3]
            for i in range(compNo):
                _SpCoi_z = SpCoi_z[i][z]
                CoSpi[i] = max(_SpCoi_z, CONST.EPS_CONST)

            # total concentration [kmol/m^3]
            CoSp = np.sum(CoSpi)

            # temperature [K]
            T = T_z[z]
            # pressure [Pa]
            P = P_z[z]

            # velocity
            v = v_z[z]

            ## calculate ##
            # mole fraction
            MoFri = np.array(
                rmtUtil.moleFractionFromConcentrationSpecies(CoSpi))

            # TODO
            # dv/dz
            # gas velocity based on interstitial velocity [m/s]
            # InGaVe = rmtUtil.calGaVeFromEOS(InGaVe0, SpCo0, CoSp, P0, P)
            # superficial gas velocity [m/s]
            # SuGaVe = InGaVe*BeVoFr
            # from ode eq. dv/dz
            SuGaVe = v

            # total flowrate [kmol/s]
            # [kmol/m^3]*[m/s]*[m^2]
            MoFlRa = CoSp*SuGaVe*CrSeAr
            # molar flowrate list [kmol/s]
            MoFlRai = MoFlRa*MoFri
            # convert to [mol/s]
            MoFlRai_Con1 = 1000*MoFlRai

            # molar flux [kmol/m^2.s]
            MoFl = MoFlRa/CrSeAr

            # volumetric flowrate [m^3/s]
            VoFlRai = calVolumetricFlowrateIG(P, T, MoFlRai_Con1)

            # mixture molecular weight [kg/mol]
            MiMoWe = rmtUtil.mixtureMolecularWeight(MoFri, MoWei, "kg/mol")

            # gas density [kg/m^3]
            GaDe = calDensityIG(MiMoWe, CoSp)
            GaDeEOS = calDensityIGFromEOS(P, T, MiMoWe)

            # NOTE
            # ergun equation
            ergA = 150*GaMiVi*SuGaVe/(PaDi**2)
            ergB = ((1-BeVoFr)**2)/(BeVoFr**3)
            ergC = 1.75*GaDe*(SuGaVe**2)/PaDi
            ergD = (1-BeVoFr)/(BeVoFr**3)
            RHS_ergun = -1*(ergA*ergB + ergC*ergD)

            # momentum balance (ergun equation)
            dxdt_P = RHS_ergun
            # dxdt.append(dxdt_P)
            P_z[z+1] = dxdt_P*dz + P_z[z]

            # NOTE
            ## kinetics ##
            # net reaction rate expression [kmol/m^3.s]
            # rf[kmol/kgcat.s]*CaBeDe[kgcat/m^3]
            # r0 = np.array(PackedBedReactorClass.modelReactions(
            #     P_z[z], T_z[z], MoFri, CaBeDe))

            # loop
            loopVars0 = (T_z[z], P_z[z], MoFri, CoSpi)
            # check unit
            r0 = np.array(reactionRateExe(
                loopVars0, varisSet, ratesSet))
            # r0 = np.copy(RiLoop)

            # loop
            Ri_z[z, :] = r0

            # REVIEW
            # component formation rate [kmol/m^3.s]
            # call
            ri = componentFormationRate(
                compNo, comList, reactionStochCoeff, Ri_z[z, :])

            # overall formation rate [kmol/m^3.s]
            OvR = np.sum(ri)

            # NOTE
            # enthalpy
            # heat capacity at constant pressure of mixture Cp [kJ/kmol.K] | [J/mol.K]
            # Cp mean list
            CpMeanList = calMeanHeatCapacityAtConstantPressure(comList, T)
            # print(f"Cp mean list: {CpMeanList}")
            # Cp mixture
            CpMeanMixture = calMixtureHeatCapacityAtConstantPressure(
                MoFri, CpMeanList)
            # print(f"Cp mean mixture: {CpMeanMixture}")

            # enthalpy change from Tref to T [kJ/kmol] | [J/mol]
            # enthalpy change
            EnChList = np.array(
                calEnthalpyChangeOfReaction(reactionListSorted, T))
            # heat of reaction at T [kJ/kmol] | [J/mol]
            HeReT = np.array(EnChList + StHeRe25)
            # overall heat of reaction [kJ/m^3.s]
            # exothermic reaction (negative sign)
            # endothermic sign (positive sign)
            OvHeReT = np.dot(Ri_z[z, :], HeReT)

            # NOTE
            # cooling temperature [K]
            Tm = ExHe['MeTe']
            # overall heat transfer coefficient [J/s.m2.K]
            U = ExHe['OvHeTrCo']
            # heat transfer area over volume [m2/m3]
            a = ExHe['EfHeTrAr']
            # heat transfer parameter [W/m^3.K] | [J/s.m^3.K]
            Ua = U*a
            # external heat [kJ/m^3.s]
            # if Tm == 0:
            #     # adiabatic
            #     Qm0 = 0
            # else:
            #     # heat added/removed from the reactor
            #     # Tm > T: heat is added (positive sign)
            #     # T > Tm: heat removed (negative sign)
            #     Qm0 = (Ua*(Tm - T))*1e-3

            Qm = rmtUtil.calHeatExchangeBetweenReactorMedium(
                Tm, T, U, a, 'kJ/m^3.s')

            # NOTE
            # velocity from global concentration
            # check BC
            if z == 0:
                # BC1
                T_b = T0
            else:
                # interior nodes
                T_b = T_z[z - 1]

            dxdt_v_T = (T_z[z] - T_b)/dz
            # CoSp x 1000
            # OvR x 1000
            dxdt_v = (1/(CoSp*1000))*((-SuGaVe/CONST.R_CONST) *
                                      ((1/T)*dxdt_P - (P/T**2)*dxdt_v_T) + OvR*1000)
            # velocity [forward value] is updated
            # backward value of temp is taken
            # dT/dt will update the old value
            v_z[z+1] = dxdt_v*dz + v_z[z]

            # NOTE
            # diff/dt
            # dxdt = []
            # matrix
            # dxdtMat = np.zeros((varNo, zNo))

            # loop vars
            const_F1 = 1/BeVoFr
            const_T1 = MoFl*CpMeanMixture
            const_T2 = 1/(CoSp*CpMeanMixture*BeVoFr + (1-BeVoFr)*CaDe*CaSpHeCa)

            # NOTE

            # concentration [mol/m^3]
            for i in range(compNo):
                # mass balance (forward difference)
                # concentration [kmol/m^3]
                # central
                Ci_c = SpCoi_z[i][z]
                # check BC
                if z == 0:
                    # BC1
                    Ci_b = SpCoi0[i]
                else:
                    # interior nodes
                    Ci_b = max(SpCoi_z[i][z - 1], CONST.EPS_CONST)
                # backward difference
                dCdz = (Ci_c - Ci_b)/dz
                # mass balance
                dxdt_F = const_F1*(-v_z[z]*dCdz - Ci_c*dxdt_v + ri[i])
                dxdtMat[i][z] = dxdt_F

            # energy balance (temperature) [K]
            # temp [K]
            T_c = T_z[z]
            # check BC
            if z == 0:
                # BC1
                T_b = T0
            else:
                # interior nodes
                T_b = T_z[z - 1]
            # backward difference
            dTdz = (T_c - T_b)/dz

            dxdt_T = const_T2*(-const_T1*dTdz + (-OvHeReT + Qm))
            dxdtMat[indexT][z] = dxdt_T

        # flat
        dxdt = dxdtMat.flatten().tolist()
        print("time: ", t)

        return dxdt

# NOTE
# dimensionless steady-state homogenous modeling

    def runN1(self):
        """
        M3 modeling case
        steady-state modeling
            not exactly plug-flow as dv/dz = 0
        unknowns: Ci, T, P
            velocity is calculated from EOS consiering feed Tf, Pf, Cf
        """
        # NOTE
        # start computation
        start = timer()

        # solver setting
        solverConfig = self.modelInput['solver-config']
        solverIVPSet = solverConfig['ivp']

        # model info
        modelId = self.modelInput['model']
        # operating conditions
        P = self.modelInput['operating-conditions']['pressure']
        T = self.modelInput['operating-conditions']['temperature']

        # reaction list
        reactionDict = self.modelInput['reactions']
        reactionList = rmtUtil.buildReactionList(reactionDict)
        # reaction rate expression
        reactionRateExpr = self.modelInput['reaction-rates']

        # component list
        compList = self.modelInput['feed']['components']['shell']

        # graph label setting
        labelList = compList.copy()
        labelList.append("Temperature")
        labelList.append("Pressure")

        # component no
        compNo = len(compList)
        indexTemp = compNo
        indexPressure = indexTemp + 1

        # reactor spec
        ReSpec = self.modelInput['reactor']
        # reactor inner diameter [m]
        ReInDi = ReSpec['ReInDi']
        # reactor length [m]
        ReLe = ReSpec['ReLe']
        # cross-sectional area [m^2]
        CrSeAr = CONST.PI_CONST*(ReInDi ** 2)/4
        # particle diameter [m]
        PaDi = ReSpec['PaDi']

        ## inlet values ##
        # inlet volumetric flowrate at T,P [m^3/s]
        VoFlRa0 = self.modelInput['feed']['volumetric-flowrate']
        # inlet species concentration [mol/m^3]
        SpCoi0 = 1*np.array(self.modelInput['feed']['concentration'])
        # inlet total concentration [mol/m^3]
        SpCo0 = np.sum(SpCoi0)
        # superficial gas velocity [m/s]
        SuGaVe0 = VoFlRa0/CrSeAr

        # mole fraction in the gas phase
        MoFri0 = np.array(rmtUtil.moleFractionFromConcentrationSpecies(SpCoi0))

        # component molecular weight [g/mol]
        MoWei = rmtUtil.extractCompData(self.internalData, "MW")

        # external heat
        ExHe = self.modelInput['external-heat']
        # cooling temperature [K]
        Tm = ExHe['MeTe']
        # overall heat transfer coefficient [J/s.m2.K]
        U = ExHe['OvHeTrCo']
        # heat transfer area over volume [m2/m3]
        a = 4/ReInDi  # ExHe['EfHeTrAr']

        # gas mixture viscosity [Pa.s]
        GaMiVi = self.modelInput['feed']['mixture-viscosity']

        # heat capacity at constant pressure of mixture Cp [kJ/kmol.K] | [J/mol.K]
        # Cp mean list
        GaCpMeanList0 = calMeanHeatCapacityAtConstantPressure(compList, T)
        # Cp mixture
        GaCpMeanMix0 = calMixtureHeatCapacityAtConstantPressure(
            MoFri0, GaCpMeanList0)

        # mixture molecular weight [kg/mol]
        MiMoWe0 = rmtUtil.mixtureMolecularWeight(MoFri0, MoWei, "kg/mol")

        # gas density [kg/m^3]
        GaDe0 = calDensityIG(MiMoWe0, SpCo0)

        # NOTE
        ### dimensionless analysis ###
        # concentration [mol/m^3]
        Cif = np.copy(SpCoi0)
        # total concentration
        Cf = SpCo0
        # temperature [K]
        Tf = T
        # pressure [Pa]
        Pf = P
        # superficial velocity [m/s]
        vf = SuGaVe0
        # length [m]
        zf = ReLe
        # heat capacity at constant pressure [J/mol.K] | [kJ/kmol.K]
        Cpif = np.copy(GaCpMeanList0)
        # mixture heat capacity [J/mol.K] | [kJ/kmol.K]
        Cpf = GaCpMeanMix0

        # gas phase
        # mass convective term - (list) [mol/m^3.s]
        _Cif = Cif if MODEL_SETTING['GaMaCoTe0'] != "MAX" else np.repeat(
            np.max(Cif), compNo)
        GaMaCoTe0 = (vf/zf)*_Cif
        # heat convective term [J/m^3.s]
        GaHeCoTe0 = (GaDe0*vf*Tf*(Cpf/MiMoWe0)/zf)

        # var no (Ci,T,P)
        varNo = compNo + 2

        # initial values (dimensionless vars)
        IV2D = np.zeros((varNo))
        _SpCoi_DiLeVa = rmtUtil.calDiLessValue(SpCoi0, Cf)
        IV2D[0:compNo] = SpCoi0/np.max(SpCoi0)
        _T_DiLeVa = rmtUtil.calDiLessValue(T, Tf, "TEMP")
        IV2D[indexTemp] = 0  # (T-Tf)/Tf
        _P_DiLeVa = rmtUtil.calDiLessValue(P, Pf)
        IV2D[indexPressure] = 1  # P/Pf
        # set
        IV = IV2D.flatten()

        # parameters
        # component data
        reactionListSorted = self.reactionListSorted
        # reaction coefficient
        reactionStochCoeff = self.reactionStochCoeffList

        # standard heat of reaction at 25C [kJ/kmol]
        StHeRe25 = np.array(
            list(map(calStandardEnthalpyOfReaction, reactionList)))

        # fun parameters
        FunParam = {
            "compList": compList,
            "const": {
                "CrSeAr": CrSeAr,
                "MoWei": MoWei,
                "StHeRe25": StHeRe25,
                "GaMiVi": GaMiVi
            },
            "ReSpec": ReSpec,
            "ExHe": {
                "OvHeTrCo": U,
                "EfHeTrAr": a,
                "MeTe": Tm
            },
            "constBC1": {
                "VoFlRa0": VoFlRa0,
                "SpCoi0": SpCoi0,
                "SpCo0": SpCo0,
                "P0": P,
                "T0": T,
                "GaDe0": GaDe0,
                "GaCpMeanMix0": GaCpMeanMix0
            },
            "reactionRateExpr": reactionRateExpr,
        }

        # dimensionless analysis parameters
        DimensionlessAnalysisParams = {
            "Cif": Cif,
            "Cf": Cf,
            "Tf": Tf,
            "Pf": Pf,
            "vf": vf,
            "zf": zf,
            "Cpif": Cpif,
            "Cpf": Cpf,
            "GaMaCoTe0": GaMaCoTe0,
            "GaHeCoTe0": GaHeCoTe0
        }

        # save data
        # timesNo = solverSetting['S3']['timesNo']
        timesNo = solverSetting['M9']['zNo']

        # REVIEW
        # domain length (dimensionless length)
        DoLe = 1

        # time span
        t = (0.0, DoLe)
        # t = np.array([0, DoLe], dtype=np.float64)
        t_span = np.array([0, DoLe])
        times = np.linspace(t_span[0], t_span[1], timesNo)

        # solver selection
        # BDF, Radau, LSODA
        solverIVP = "LSODA" if solverIVPSet == 'default' else solverIVPSet
        # set
        funSet = PackedBedHomoReactorClass.modelEquationN1
        paramsSet = (reactionListSorted, reactionStochCoeff,
                     FunParam, DimensionlessAnalysisParams)
        # ode call
        sol = solve_ivp(funSet, t, IV, method=solverIVP,
                        t_eval=times, args=(paramsSet,))

        # ode result
        successStatus = sol.success
        dataX = sol.t
        # all results
        dataYs = sol.y
        # concentration [mol/m^3]
        dataYs1 = sol.y[0:compNo, :]
        labelListYs1 = labelList[0:compNo]
        # REVIEW
        # convert molar flowrate to mole fraction
        # convert concentration to mole fraction
        dataYs1_Ctot = np.sum(dataYs1, axis=0)
        dataYs1_MoFri = dataYs1/dataYs1_Ctot
        # temperature
        dataYs2 = sol.y[indexTemp, :]
        labelListYs3 = labelList[indexTemp]
        # pressure
        dataYs3 = sol.y[indexPressure, :]

        # FIXME
        # build matrix
        _dataYs = np.concatenate(
            (dataYs1_MoFri, [dataYs2]), axis=0)

        # NOTE
        # end of computation
        end = timer()
        elapsed = roundNum(end - start)

        # plot info
        plotTitle = f"Steady-State Modeling {modelId} with timesNo: {timesNo} within {elapsed}"

        # check
        if successStatus is True:
            # plot setting: build (x,y) series
            XYList = pltc.plots2DSetXYList(dataX, _dataYs)
            # -> add label
            dataList = pltc.plots2DSetDataList(XYList, labelList)
            # datalists
            dataLists = [dataList[0:compNo],
                         dataList[indexTemp]]
            # select datalist
            _dataListsSelected = selectFromListByIndex([0, -1], dataLists)
            # subplot result
            pltc.plots2DSub(_dataListsSelected, "Reactor Length (m)",
                            "Concentration (mol/m^3)", plotTitle)

        else:
            _dataYs = []
            XYList = []
            dataList = []

        # return
        res = {
            "dataYs": _dataYs,
            "XYList": XYList,
            "dataList": dataList
        }

        return res

    def modelEquationN1(t, y, paramsSet):
        """
        mass, energy, and momentum balance equations
        modelParameters:
            reactionListSorted: reactant/product and coefficient lists
            reactionStochCoeff: reaction stoichiometric coefficient
            FunParam:
                compList: component list
                const
                    CrSeAr: reactor cross sectional area [m^2]
                    MoWei: component molecular weight [g/mol]
                    StHeRe25: standard heat of reaction at 25C [kJ/kmol] | [J/mol]
                    GaMiVi: gas mixture viscosity [Pa.s]
                ReSpec: reactor spec
                ExHe: exchange heat spec
                    OvHeTrCo: overall heat transfer coefficient [J/m^2.s.K]
                    EfHeTrAr: effective heat transfer area [m^2]
                    MeTe: medium temperature [K]
                constBC1:
                    VoFlRa0: inlet volumetric flowrate [m^3/s],
                    SpCoi0: species concentration [kmol/m^3],
                    SpCo0: total concentration [kmol/m^3]
                    P0: inlet pressure [Pa]
                    T0: inlet temperature [K]
                    GaDe0: gas density [kg/m^3]
                    GaCpMeanMix0: heat capacity at constant pressure of gas mixture [kJ/kmol.K] | [J/mol.K]
                reactionRateExpr: reaction rate expressions
            DimensionlessAnalysisParams:
                Cif: feed species concentration [mol/m^3]
                Cf: feed concentration [mol/m^3]
                Tf: feed temperature [K]
                vf: feed superficial velocity [m/s]
                zf: domain length [m]
                Cpif: feed heat capacity at constat pressure [kJ/kmol.K] | [J/mol.K]
                Cpf: mixture heat capacity [J/mol.K] | [kJ/kmol.K]
                GaMaCoTe0: feed mass convective term of gas phase [mol/m^3.s]
                GaHeCoTe0: feed heat convective term of gas phase [J/m^3.s]
        """
        # set
        reactionListSorted, reactionStochCoeff, FunParam, DimensionlessAnalysisParams = paramsSet
        # fun params
        # component symbol list
        comList = FunParam['compList']
        # const ->
        const = FunParam['const']
        # cross-sectional area [m^2]
        CrSeAr = const['CrSeAr']
        # component molecular weight [g/mol]
        MoWei = const['MoWei']
        # standard heat of reaction at 25C [kJ/kmol] | [J/mol]
        StHeRe25 = const['StHeRe25']
        # gas viscosity [Pa.s]
        GaMiVi = const['GaMiVi']
        # reactor spec ->
        ReSpec = FunParam['ReSpec']
        # bed void fraction - porosity
        BeVoFr = ReSpec['BeVoFr']
        # bulk density (catalyst bed density)
        CaBeDe = ReSpec['CaBeDe']
        # particle diameter [m]
        PaDi = ReSpec['PaDi']
        # exchange heat spec ->
        ExHe = FunParam['ExHe']

        # boundary conditions constants
        constBC1 = FunParam['constBC1']
        ## inlet values ##
        # inlet volumetric flowrate at T,P [m^3/s]
        VoFlRa0 = constBC1['VoFlRa0']
        # inlet species concentration [mol/m^3]
        SpCoi0 = constBC1['SpCoi0']
        # inlet total concentration [mol/m^3]
        SpCo0 = constBC1['SpCo0']
        # inlet pressure [Pa]
        P0 = constBC1['P0']
        # inlet temperature [K]
        T0 = constBC1['T0']
        # gas density [kg/m^3]
        GaDe0 = constBC1['GaDe0']
        # heat capacity at constant pressure [kJ/kmol.K] | [J/mol.K]
        GaCpMeanMix0 = constBC1['GaCpMeanMix0']

        # reaction rate expressions
        reactionRateExpr = FunParam['reactionRateExpr']
        # using equation
        varisSet = reactionRateExpr['VARS']
        ratesSet = reactionRateExpr['RATES']

        # dimensionless analysis params
        #  feed species concentration [kmol/m^3]
        Cif = DimensionlessAnalysisParams['Cif']
        #  feed concentration [kmol/m^3]
        Cf = DimensionlessAnalysisParams['Cf']
        # feed temperature [K]
        Tf = DimensionlessAnalysisParams['Tf']
        # feed pressure [Pa]
        Pf = DimensionlessAnalysisParams['Pf']
        # feed superficial velocity [m/s]
        vf = DimensionlessAnalysisParams['vf']
        # domain length [m]
        zf = DimensionlessAnalysisParams['zf']
        # feed heat capacity at constat pressure
        Cpif = DimensionlessAnalysisParams['Cpif']
        # mixture feed heat capacity at constat pressure
        Cpf = DimensionlessAnalysisParams['Cpf']
        # feed mass convective term of gas phase [kmol/m^3.s]
        GaMaCoTe0 = DimensionlessAnalysisParams['GaMaCoTe0']
        # feed heat convective term of gas phase [kJ/m^3.s]
        GaHeCoTe0 = DimensionlessAnalysisParams['GaHeCoTe0']

        # calculate
        # molar flowrate [kmol/s]
        MoFlRa0 = SpCo0*VoFlRa0
        # superficial gas velocity [m/s]
        InGaVe0 = VoFlRa0/(CrSeAr*BeVoFr)
        # interstitial gas velocity [m/s]
        SuGaVe0 = InGaVe0*BeVoFr

        # components no
        # y: component molar flowrate, total molar flux, temperature, pressure
        compNo = len(comList)
        indexT = compNo
        indexP = indexT + 1

        # NOTE
        ### dimensionless vars ###
        yLoop = np.array(y)
        # concentration species [mol/m^3] => []
        CoSpi = yLoop[0:compNo]
        # temperature [K] => []
        T = yLoop[indexT]
        # pressure [Pa] => []
        P = yLoop[indexP]

        # REVIEW
        # dimensionless analysis: real value
        SpCoi0_Set = SpCoi0 if MODEL_SETTING['GaMaCoTe0'] != "MAX" else np.max(
            SpCoi0)
        CoSpi_ReVa = rmtUtil.calRealDiLessValue(
            CoSpi, SpCoi0_Set)

        # total concentration [mol/m^3]
        CoSp = np.sum(CoSpi)
        # dimensionless analysis: real value
        CoSp_ReVa = np.sum(CoSpi_ReVa)

        # temperature [K]
        T_ReVa = rmtUtil.calRealDiLessValue(T, Tf, "TEMP")

        # pressure [Pa]
        P_ReVa = rmtUtil.calRealDiLessValue(P, Pf)

        # mole fraction
        MoFri = np.array(
            rmtUtil.moleFractionFromConcentrationSpecies(CoSpi_ReVa))

        # gas velocity based on interstitial velocity [m/s]
        InGaVe = rmtUtil.calGaVeFromEOS(InGaVe0, SpCo0, CoSp_ReVa, P0, P)
        # dimensionless analysis
        InGaVe_DiLeVa = rmtUtil.calDiLessValue(InGaVe, InGaVe0)
        # superficial gas velocity [m/s]
        SuGaVe = InGaVe*BeVoFr
        # dimensionless analysis
        SuGaVe_DiLeVa = SuGaVe/SuGaVe0

        # total flowrate [mol/s]
        # [mol/m^3]*[m/s]*[m^2]
        MoFlRa = CoSp_ReVa*SuGaVe*CrSeAr
        # molar flowrate list [mol/s]
        MoFlRai = MoFlRa*MoFri

        # FIXME
        # molar flux [mol/m^2.s]
        MoFl = MoFlRa/CrSeAr

        # volumetric flowrate [m^3/s]
        VoFlRai = calVolumetricFlowrateIG(P, T, MoFlRai)

        # mixture molecular weight [kg/mol]
        MiMoWe = rmtUtil.mixtureMolecularWeight(MoFri, MoWei, "kg/mol")

        # gas density [kg/m^3]
        GaDe = calDensityIG(MiMoWe, CoSp_ReVa)
        GaDeEOS = calDensityIGFromEOS(P, T, MiMoWe)
        # dimensionless value
        GaDe_DiLeVa = rmtUtil.calDiLessValue(GaDe, GaDe0)

        # NOTE
        # momentum equation
        # REVIEW
        # ergun equation
        ergA = 150*GaMiVi*SuGaVe/(PaDi**2)
        ergB = ((1-BeVoFr)**2)/(BeVoFr**3)
        ergC = 1.75*GaDe*(SuGaVe**2)/PaDi
        ergD = (1-BeVoFr)/(BeVoFr**3)
        # dimensionless term
        ergBeta = (Pf/zf)
        RHS_ergun = -1*(ergA*ergB + ergC*ergD)/ergBeta

        # NOTE
        # kinetics
        # component formation rate [mol/m^3.s]
        # loop
        loopVars0 = (T_ReVa, P_ReVa, MoFri, CoSpi_ReVa)
        # check unit
        r0 = np.array(reactionRateExe(
            loopVars0, varisSet, ratesSet))

        # loop
        Ri = r0

        # component formation rate [mol/m^3.s]
        # rf[mol/kgcat.s]*CaBeDe[kgcat/m^3]
        # call [mol/m^3.s]
        ri = componentFormationRate(
            compNo, comList, reactionStochCoeff, Ri)

        # overall formation rate [mol/m^3.s]
        OvR = np.sum(ri)

        # enthalpy
        # heat capacity at constant pressure of mixture Cp [kJ/kmol.K] | [J/mol.K]
        # Cp mean list
        CpMeanList = calMeanHeatCapacityAtConstantPressure(comList, T_ReVa)
        # print(f"Cp mean list: {CpMeanList}")
        # Cp mixture
        GaCpMeanMix = calMixtureHeatCapacityAtConstantPressure(
            MoFri, CpMeanList)
        # dimensionless analysis
        GaCpMeanMix_DiLeVa = rmtUtil.calDiLessValue(
            GaCpMeanMix, GaCpMeanMix0)
        # effective heat capacity - gas phase [kJ/kmol.K] | [J/mol.K]
        GaCpMeanMixEff = GaCpMeanMix*BeVoFr
        # dimensionless analysis
        GaCpMeanMixEff_DiLeVa = GaCpMeanMix_DiLeVa*BeVoFr

        # enthalpy change from Tref to T [kJ/kmol] | [J/mol]
        # enthalpy change
        EnChList = np.array(calEnthalpyChangeOfReaction(
            reactionListSorted, T_ReVa))
        # heat of reaction at T [kJ/kmol] | [J/mol]
        HeReT = np.array(EnChList + StHeRe25)
        # overall heat of reaction [J/m^3.s]
        OvHeReT = np.dot(Ri, HeReT)

        # NOTE
        #
        # cooling temperature [K]
        Tm = ExHe['MeTe']
        # overall heat transfer coefficient [J/s.m2.K]
        U = ExHe['OvHeTrCo']
        # heat transfer area over volume [m2/m3]
        a = ExHe['EfHeTrAr']
        # external heat [J/m^3.s]
        # Qm = Ua*(Tm - T)
        Qm = rmtUtil.calHeatExchangeBetweenReactorMedium(
            Tm, T_ReVa, U, a, 'J/m^3.s')

        # NOTE
        # diff/dt
        dxdt = []
        constC1 = 1/SuGaVe_DiLeVa
        constT1 = 1/(GaDe_DiLeVa*GaCpMeanMixEff_DiLeVa*InGaVe_DiLeVa)

        # mass balance (concentration) [mol/m^3]
        for i in range(compNo):
            dxdt_Ci = constC1*(ri[i]/GaMaCoTe0)
            dxdt.append(dxdt_Ci)

        # energy balance (temperature) [K]
        dxdt_T = constT1*((-OvHeReT + Qm)/GaHeCoTe0)
        dxdt.append(dxdt_T)

        # momentum balance (ergun equation)
        dxdt_P = RHS_ergun
        dxdt.append(dxdt_P)

        return dxdt