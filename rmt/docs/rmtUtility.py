# GENERAL EQUATIONS
# ------------------


# import packages/modules
import numpy as np
import re
from typing import List
from core import constants as CONST
# add err class

#


class rmtUtilityClass:
    #
    def __init__(self):
        pass

    @staticmethod
    def mixtureMolecularWeight(MoFri, MWi):
        """
        calculate mixture molecular weight [g/mol]
        args:
            MoFri: component mole fraction
            MWi: molecular weight [g/mol]
        """
        # try/exception
        try:
            # check
            if not isinstance(MoFri, np.ndarray):
                if isinstance(MoFri, List):
                    MoFri0 = np.array(MoFri)
            else:
                MoFri0 = np.copy(MoFri)

            if not isinstance(MWi, np.ndarray):
                if isinstance(MWi, List):
                    MWi0 = np.array(MWi)
            else:
                MWi0 = np.copy(MWi)

            # check
            if MoFri0.size != MWi0.size:
                raise Exception("elements are not equal")
            #
            MixMoWe = np.dot(MoFri0, MWi0)
            return MixMoWe
        except Exception as e:
            print(e)

    @staticmethod
    def volumetricFlowrateSTP(VoFlRa, P, T):
        """
            calculate volumetric flowrate at STP conditions
            VoFlRa []
            P [Pa]
            T [K]
            VoFlRaSTP []
        """
        VoFlRaSTP = VoFlRa*(P/CONST.Pstp)*(CONST.Tstp/T)
        return VoFlRaSTP

    @staticmethod
    def VoFlRaSTPToMoFl(VoFlRaSTP):
        """
            convert volumetric flowrate [stp] to molar flowrate [ideal gas]
            VoFlRaSTP [m^3/s]
            MoFlRaIG [mol/s]
        """
        MoFlRaIG = (VoFlRaSTP/0.02241)
        return MoFlRaIG

    @staticmethod
    def reactorCrossSectionArea(BePo, ReDi):
        """
            calculate reactor cross section area
            BePo: bed porosity [-]
            ReDi: reactor diameter [m]
            ReCrSeAr [m^2]
        """
        ReCrSeAr = BePo*(CONST.PI_CONST*(ReDi**2)/4)
        return ReCrSeAr

    @staticmethod
    def componentInfo(compList):
        """
            return component no. and name (symbol)
            args:
                compList: list of components' symbols
        """
        # try/except
        try:
            # component no
            if isinstance(compList, List):
                compNo = len(compList)
            else:
                raise

            # res
            res = {
                "compNo": compNo,
                "compList": compList
            }

            return res
        except Exception as e:
            raise

    @staticmethod
    def buildReactionList(reactionDict):
        """
            return reaction list [string]
            args:
                reactionDict: reaction dict
        """
        # try/except
        try:
            dictVal = reactionDict.values()
            return list(dictVal)
        except Exception as e:
            raise

    @staticmethod
    def buildReactionCoefficient(reactionDict):
        """
            build reaction coefficient
            args:
                reactionDict: reaction dict
        """
        # try/except
        try:
            # reaction list
            reactionList = rmtUtilityClass.buildReactionList(reactionDict)
            print(f"reaction list: {reactionList}")

            # sorted reaction list
            reactionListSorted = []

            for reaction in reactionList:
                # analyze reactions
                reaType = reaction.replace("<", "").replace(">", "")
                # reactant/products list
                compR = reaType.replace(r" ", "").split("=")
                print(f"compR1 {compR}")

                # componets
                reactantList = re.findall(
                    r"([0-9.]*)([a-zA-Z0-9.]+)", compR[0])
                print(f"reactantList {reactantList}")
                productList = re.findall(r"([0-9.]*)([a-zA-Z0-9.]+)", compR[1])
                print(f"productList {productList}")
                print("------------------")

                # reactant coefficient
                _loop1 = [{"symbol": i[1], "coeff": -1*float(i[0])} if len(i[0]) != 0 else {"symbol": i[1], "coeff": -1.0}
                          for i in reactantList]
                # product coefficient
                _loop2 = [{"symbol": i[1], "coeff": float(i[0])} if len(i[0]) != 0 else {"symbol": i[1], "coeff": 1.0}
                          for i in productList]
                # store dict
                _loop3 = {
                    "reactants": _loop1,
                    "products": _loop2
                }
                # store
                reactionListSorted.append(_loop3)

            # print("reactionListSorted: ", reactionListSorted)
            # res
            return reactionListSorted
        except Exception as e:
            raise

    @staticmethod
    def buildReactionCoeffVector(reactionListSorted):
        """
            build reaction coeff vector
        """
        # try/except
        try:
            # build list
            reactionCoeff = []
            #
            for element in reactionListSorted:
                # reactant coefficient
                _loop1 = [[item['symbol'], float(item['coeff'])]
                          for item in element['reactants']]
                # product coefficient
                _loop2 = [[item['symbol'], float(item['coeff'])]
                          for item in element['products']]
                # vector
                _loop3 = []
                _loop3.extend(_loop1)
                _loop3.extend(_loop2)
                _loop4 = _loop3.copy()
                reactionCoeff.append(_loop4)

            # res
            return reactionCoeff
        except Exception as e:
            raise

    @ staticmethod
    def buildreactionRateExpr(reactionRateExprDict):
        """
        build a list of reaction rate expression
        args:
            reactionRateExprDict: a dictionary contains all reaction rate expr
            {"R1": "r1(C,T,y), ...}
        """
        # try/except
        try:
            print(0)
        except Exception as e:
            raise

    @ staticmethod
    def moleFractionFromConcentrationSpecies(CoSpi):
        """
        calculate: mole fraction
        args:
            CoSpi: concentration species [mol/m^3]
        """
        # try/except
        try:
            MoFri = CoSpi/np.sum(CoSpi)
            return MoFri
        except Exception as e:
            raise

    @staticmethod
    def buildComponentList(componentDataDict):
        """ 
        build component list participated in the reaction
        this list is used for component availability in the app database
        """
        # try/except
        try:
            # all
            compList0 = []
            # shell
            shellComp = componentDataDict['shell']
            if shellComp:
                compList0.extend(shellComp)
            # tube
            tubeComp = componentDataDict['tube']
            if tubeComp:
                compList0.extend(tubeComp)
            # medium
            mediumComp = componentDataDict['medium']
            if mediumComp:
                compList0.extend(mediumComp)
            # all
            compList = list(dict.fromkeys(compList0))
            return compList

        except Exception as e:
            raise
