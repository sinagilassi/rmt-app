# FINITE DIFFERENCE METHOD
# -------------------------

# import module/packages
import numpy as np
from solvers.solSetting import DIFF_SETTING


def FiDiBuildCMatrix(compNo, DoLe, rNo, yi, params, mode="default"):
    '''
    build concentration residual matrix [R]
    args:
        compNo: component no
        DoLe: domain length [m]
        rNo: number of finite difference points
        yi: y variables
        params: 
            DiCoi: diffusivity coefficient of components [m^2/s]
            MaTrCoi: mass transfer coefficient [m/s]
            Ri: formation rate of component [kmol/m^3.s] | [mol/m^3.s]
            SpCoiBulk: species concentration of component in the bulk phase [kmol/m^3] | [mol/m^3]
            CaPo: catalyst porosity
    '''
    # try/except
    try:
        # number of finite differene points
        # rNo
        # number of elements
        NoEl_FiDi = rNo - 1
        # number of total nodes
        N = rNo*compNo
        # dr size [m]
        dr = 1/NoEl_FiDi
        # formula
        rp = DoLe

        # NOTE
        ### matrix structure ##
        # residual matrix
        AMatShape = rNo
        A = np.zeros(AMatShape)

        # params
        DiCoi, MaTrCoi, Ri, SpCoiBulk, CaPo, SoMaDiTe0 = params

        # concentration

        for i in range(rNo):
            # dr distance
            ri = 1 if i == 0 else i*dr
            # constant
            const1 = (DiCoi/(dr**2))
            const2 = 2*DiCoi/(ri*2*dr)

            # reaction term
            _Ri = (1 - CaPo)*Ri[i]*(rp**2)

            if i == 0:
                A[i] = 3*const1*(2*yi[i+1] - 2*yi[i]) + _Ri
            elif i > 0 and i < rNo-1:
                A[i] = const1*(yi[i-1] - 2*yi[i] + yi[i+1]) + \
                    const2*(yi[i+1] - yi[i-1]) + _Ri
            elif i == rNo-1:
                # const
                alpha = (rp*MaTrCoi)/DiCoi
                # ghost point y[N+1]
                yN__1 = (2*dr)*alpha*(yi[i] - SpCoiBulk) + yi[i-1]
                A[i] = const1*(yi[i-1] - 2*yi[i] + yN__1) + \
                    const2*(yN__1 - yi[i-1]) + _Ri

        # flip
        A_Flip = np.flip(A)

        # check
        A_Res = A_Flip if mode == "default" else A

        # res
        return A_Res
    except Exception as e:
        raise


def FiDiBuildCiMatrix(compNo, DoLe, rNo, yi, params):
    '''
    build concentration residual matrix [R]
    args:
        compNo: component no
        DoLe: domain length [m]
        rNo: number of finite difference points
        **args: 
            DiCoi: diffusivity coefficient of components [m^2/s]
            MaTrCoi: mass transfer coefficient [m/s]
            Ri: formation rate of component [kmol/m^3.s] | [mol/m^3.s]
            SpCoiBulk: species concentration of component in the bulk phase [kmol/m^3] | [mol/m^3]
    '''
    # try/except
    try:
        # number of finite differene points
        # rNo
        # number of elements
        NoEl_FiDi = rNo - 1
        # number of total nodes
        N = rNo*compNo
        # dr size [m]
        dr = DoLe/NoEl_FiDi
        # formula
        rp = DoLe

        # NOTE
        ### matrix structure ##
        # residual matrix
        AMatShape = (compNo, rNo)
        A = np.zeros(AMatShape)

        # params
        DiCoi, MaTrCoi, Ri, SpCoiBulk = params

        # concentration
        for c in range(compNo):
            # component yj
            SpCoi = yi[i, :]

            for i in range(rNo):
                # dr distance
                ri = i*dr
                # constant
                const1 = (DiCoi[c]/dr**2)
                const2 = 2*DiCoi[c]/(ri*2*dr)

                # reaction term
                _Ri = Ri[i, c]*(rp**2)

                if i == 0:
                    A[c][i] = 3*const1(2*SpCoi[i+1] - 2*SpCoi[i]) + _Ri

                elif i > 0 and i < rNo-1:
                    A[c][i] = const1*(SpCoi[i-1] - 2*SpCoi[i] + SpCoi[i+1]) + \
                        const2*(SpCoi[i+1] - SpCoi[i-1]) + _Ri
                elif i == rNo-1:
                    # const
                    alpha = MaTrCoi[c]/DiCoi[c]
                    # ghost point y[N+1]
                    yN__1 = (2*dr)*alpha*(SpCoi[i] - SpCoiBulk[i]) + SpCoi[i-1]
                    A[c][i] = const1*(SpCoi[i-1] - 2*SpCoi[i] + yN__1) + \
                        const2*(yN__1 - SpCoi[i-1]) + _Ri

        # res
        return A
    except Exception as e:
        raise


def FiDiBuildTMatrix(compNo, DoLe, rNo, yi, params, mode="default"):
    '''
    build temperature residual matrix [R]
    args:
        compNo: component no
        DoLe: domain length [m]
        rNo: number of finite difference points
        **args: 
            CaThCo: thermal conductivity of catalyst [kJ/s.m.K] | [J/s.m.K]
            HeTrCo: heat transfer coefficient [kJ/m^2.s.K] | [J/m^2.s.K] .
            OvHeReT: overall heat of reaction [kJ/m^3.s] | [J/m^3.s]
            TBulk: temperature of component in the bulk phase [K]
            optional:
                Ri: formation rate of component [kmol/m^3.s] | [mol/m^3.s]
                dHi: enthalpy of reactions [kJ/kmol] | [J/kmol]
    '''
    # try/except
    try:
        # number of finite differene points
        # rNo
        # number of elements
        NoEl_FiDi = rNo - 1
        # number of total nodes
        N = rNo*compNo
        # dr size [m]
        dr = 1/NoEl_FiDi
        # formula
        rp = DoLe

        # NOTE
        ### matrix structure ##
        # residual matrix
        AMatShape = (rNo)
        A = np.zeros(AMatShape)

        # params
        CaThCo, HeTrCo, OvHeReT, TBulk, CaPo = params

        # temperature
        # element of yj
        Ti = yi

        # constant
        const1 = (CaThCo/(dr**2))

        for i in range(rNo):
            # dr distance
            ri = 1 if i == 0 else i*dr
            const2 = 2*CaThCo/(ri*2*dr)

            # reaction term
            _dHRi = (1 - CaPo)*OvHeReT[i]*(rp**2)

            if i == 0:
                A[i] = 3*const1*(2*Ti[i+1] - 2*Ti[i]) + _dHRi
            elif i > 0 and i < rNo-1:
                A[i] = const1*(Ti[i-1] - 2*Ti[i] + Ti[i+1]) + \
                    const2*(Ti[i+1] - Ti[i-1]) + _dHRi
            elif i == rNo-1:
                # const
                alpha = -1*(rp*HeTrCo)/CaThCo
                # ghost point y[N+1]
                yN__1 = (2*dr)*alpha*(Ti[i] - TBulk) + Ti[i-1]
                A[i] = const1*(Ti[i-1] - 2*Ti[i] + yN__1) + \
                    const2*(yN__1 - Ti[i-1]) + _dHRi

        # flip
        A_Flip = np.flip(A)

        # check
        A_Res = A_Flip if mode == "default" else A

        # res
        return A_Res
    except Exception as e:
        raise


def FiDiSetMatrix(compNo, DoLe, rNo, yj, params):
    '''
    BC1 
    args:
        compNo: component no
        DoLe: domain length [m]
        rNo: number of finite difference points
        **argsVal
            DiCoi: diffusivity coefficient of components [m^2/s]
            MaTrCoi: mass transfer coefficient [m/s]
            Ri: formation rate of component [kmol/m^3.s] | [mol/m^3.s]
            SpCoiBulk: species concentration of component in the bulk phase [kmol/m^3] | [mol/m^3]
            CaPo: catalyst porosity
    '''
    try:
        # number of finite differene points
        # rNo
        # number of elements
        NoEl_FiDi = rNo - 1
        # number of total nodes
        N = rNo*compNo
        # dr size [m]
        dr = 1/NoEl_FiDi
        # formula
        rp = DoLe

        # NOTE
        ### matrix structure ##
        # LHS matrix
        AMatShape = (rNo, rNo)
        A = np.zeros(AMatShape)
        # RHS matrix
        fMatShape = (rNo, 1)
        f = np.zeros(fMatShape)
        # share matrix
        sMatShape = (rNo, 1)
        s = np.zeros(sMatShape)

        # params
        DiCoi, MaTrCoi, Ri, SpCoiBulk, CaPo = params

        for i in range(rNo):
            # dr distance
            ri = 1 if i == 0 else i*dr
            # constant
            alpha = (DiCoi/(dr**2))
            beta = 2*DiCoi/(ri*2*dr)

            # reaction term
            _Ri = (1 - CaPo)*Ri[i]*(rp**2)

            if i == 0:
                # BC1
                A[i, i] = -3*alpha*2
                A[i, i+1] = 3*alpha*2
                f[i] = 1*_Ri
                s[i] = 0
            elif i > 0 and i < rNo-1:
                # interrior points
                A[i, i-1] = alpha - beta
                A[i, i] = -2*alpha
                A[i, i+1] = alpha + beta
                f[i] = 1*_Ri
                s[i] = 0
            elif i == rNo-1:
                # BC2
                # const
                alphaStar = (2*dr*rp*MaTrCoi)/DiCoi
                # ghost point y[N+1]
                A[i, i-1] = 2*alpha
                A[i, i] = -2*alpha + alphaStar*(alpha + beta)
                f[i] = 1*_Ri
                s[i] = -alphaStar*(alpha + beta)

        # res
        res = A*yj + f + s

        # return
        return res
    except Exception as e:
        raise

# NOTE
# dimensionless type


def FiDiBuildCMatrix_DiLe(compNo, DoLe, rNo, yi, params, mode="default"):
    '''
    build concentration residual matrix [R]
    args:
        compNo: component no
        DoLe: domain length [m]
        rNo: number of finite difference points
        yi: y variables
        params: 
            DiCoi: diffusivity coefficient of components [m^2/s]
            MaTrCoi: mass transfer coefficient [m/s]
            Ri: formation rate of component [kmol/m^3.s] | [mol/m^3.s]
            SpCoiBulk: species concentration of component in the bulk phase [kmol/m^3] | [mol/m^3]
            CaPo: catalyst porosity
    '''
    # try/except
    try:
        # number of finite differene points
        # rNo
        # number of elements
        NoEl_FiDi = rNo - 1
        # number of total nodes
        N = rNo*compNo
        # dr size [m]
        dr = 1/NoEl_FiDi
        # formula
        rp = DoLe

        # NOTE
        ### matrix structure ##
        # residual matrix
        AMatShape = rNo
        A = np.zeros(AMatShape)

        # params
        DiCoi_DiLeVa, MaTrCoi, Ri, SpCoiBulk, CaPo, SoMaDiTe0, GaDii0, rf = params

        # concentration

        for i in range(rNo):
            # dr distance
            ri = 1 if i == 0 else i*dr

            # constant
            const1 = (DiCoi_DiLeVa/(dr**2))
            const2 = 2*DiCoi_DiLeVa/(ri*2*dr)

            # reaction term
            _Ri = (1/SoMaDiTe0)*(1 - CaPo)*Ri[i]

            if i == 0:
                A[i] = 3*const1*(2*yi[i+1] - 2*yi[i]) + _Ri
            elif i > 0 and i < rNo-1:
                A[i] = const1*(yi[i-1] - 2*yi[i] + yi[i+1]) + \
                    const2*(yi[i+1] - yi[i-1]) + _Ri
            elif i == rNo-1:
                # const
                alpha = rf/GaDii0
                beta = MaTrCoi/DiCoi_DiLeVa
                # ghost point y[N+1]
                yN__1 = (2*dr)*alpha*beta*(yi[i] - SpCoiBulk) + yi[i-1]
                A[i] = const1*(yi[i-1] - 2*yi[i] + yN__1) + \
                    const2*(yN__1 - yi[i-1]) + _Ri

        # flip
        A_Flip = np.flip(A)

        # check
        A_Res = A_Flip if mode == "default" else A

        # res
        return A_Res
    except Exception as e:
        raise


def FiDiBuildTMatrix_DiLe(compNo, DoLe, rNo, yi, params, mode="default"):
    '''
    build temperature residual matrix [R]
    args:
        compNo: component no
        DoLe: domain length [m]
        rNo: number of finite difference points
        **args: 
            CaThCo: thermal conductivity of catalyst [kJ/s.m.K] | [J/s.m.K]
            HeTrCo: heat transfer coefficient [kJ/m^2.s.K] | [J/m^2.s.K] .
            OvHeReT: overall heat of reaction [kJ/m^3.s] | [J/m^3.s]
            TBulk: temperature of component in the bulk phase [K]
            optional:
                Ri: formation rate of component [kmol/m^3.s] | [mol/m^3.s]
                dHi: enthalpy of reactions [kJ/kmol] | [J/kmol]
    '''
    # try/except
    try:
        # number of finite differene points
        # rNo
        # number of elements
        NoEl_FiDi = rNo - 1
        # number of total nodes
        N = rNo*compNo
        # dr size [m]
        dr = 1/NoEl_FiDi
        # formula
        rp = DoLe

        # NOTE
        ### matrix structure ##
        # residual matrix
        AMatShape = (rNo)
        A = np.zeros(AMatShape)

        # params
        CaThCo_DiLeVa, HeTrCo, OvHeReT, TBulk, CaPo, SoHeDiTe0, CaThCo, rf = params

        # temperature
        # element of yj
        Ti = yi

        # constant
        const1 = CaThCo_DiLeVa/(dr**2)

        for i in range(rNo):
            # dr distance
            ri = 1 if i == 0 else i*dr
            const2 = 2*CaThCo_DiLeVa/(ri*2*dr)

            # reaction term
            _dHRi = (1/SoHeDiTe0)*(1 - CaPo)*OvHeReT[i]

            if i == 0:
                A[i] = 3*const1*(2*Ti[i+1] - 2*Ti[i]) + _dHRi
            elif i > 0 and i < rNo-1:
                A[i] = const1*(Ti[i-1] - 2*Ti[i] + Ti[i+1]) + \
                    const2*(Ti[i+1] - Ti[i-1]) + _dHRi
            elif i == rNo-1:
                # const
                alpha = rf/CaThCo
                beta = -1*HeTrCo/CaThCo_DiLeVa
                # ghost point y[N+1]
                yN__1 = (2*dr)*alpha*beta*(Ti[i] - TBulk) + Ti[i-1]
                A[i] = const1*(Ti[i-1] - 2*Ti[i] + yN__1) + \
                    const2*(yN__1 - Ti[i-1]) + _dHRi

        # flip
        A_Flip = np.flip(A)

        # check
        A_Res = A_Flip if mode == "default" else A

        # res
        return A_Res
    except Exception as e:
        raise


def FiDiDerivative1(F, dz, mode):
    """
    calculate approximate first derivate of function F
    args:
        F: value at i-1, i, i+1
        dz: step size 
        mode: derivate algorithm 
            backward: -1
            central: 0
            forward: 1
    output:
        dF/dt: value
    """
    # try/except
    try:
        F_b = F[0]
        F_c = F[1]
        F_f = F[2]
        if mode == DIFF_SETTING['BD']:
            dFdz = (F_c - F_b)/dz
        elif mode == DIFF_SETTING['CD']:
            dFdz = (F_f - F_b)/(2*dz)
        elif mode == DIFF_SETTING['FD']:
            dFdz = (F_f - F_c)/dz
        return dFdz
    except Exception as e:
        raise


def FiDiDerivative2(F, dz, mode):
    """
    calculate approximate second derivate of function F
    args:
        F: value at i-2, i-1, i, i+1, i+2
        dz: step size 
        mode: derivate algorithm 
            backward: -1
            central: 0
            forward: 1
    output:
        d2F/dz2: value
    """
    # try/except
    try:
        F_bb = F[0]
        F_b = F[1]
        F_c = F[2]
        F_f = F[3]
        F_ff = F[4]
        if mode == DIFF_SETTING['BD']:
            d2Fdz2 = (F_c - 2*F_b + F_bb)/(dz**2)
        elif mode == DIFF_SETTING['CD']:
            d2Fdz2 = (F_f - 2*F_c + F_b)/(dz**2)
        elif mode == DIFF_SETTING['FD']:
            d2Fdz2 = (F_ff - 2*F_f + F_c)/(dz**2)
        return d2Fdz2
    except Exception as e:
        raise
