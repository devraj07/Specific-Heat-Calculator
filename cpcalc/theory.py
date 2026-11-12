"""Theory pages shown in the UI (LaTeX). Data only: every page has a short text, numbered equations
(the numbers are those of the spec), the conditions under which they hold, what goes in and out, where to
type the inputs in the app, and where the code uses them.

Optional keys per page: "gives" (inputs -> outputs), "where" (where in the app), "next" (the next page),
"diagram" (a Graphviz DOT string)."""

FLOW = r"""
digraph cpcalc {
  rankdir=TB; bgcolor="transparent"; nodesep=0.25; ranksep=0.35;
  node [shape=box, style="rounded,filled", fillcolor="#eef2f7", fontcolor="#111827", color="#64748b", fontname="Helvetica", fontsize=11];
  edge [color="#64748b", fontname="Helvetica", fontsize=10, fontcolor="#64748b"];
  S [label="1  Describe the sample\nT, P, phases, amounts  (tab 1)", fillcolor="#dbeafe"];
  P [label="2  c_p of every phase", fillcolor="#dbeafe"];
  L [label="Liquid or solid\ndata first; solids: Debye\n(page 3)"];
  G [label="Gas\nPeng-Robinson or ideal gas\n(page 4)"];
  M [label="Mixture\nideal + excess function:\nMargules or NRTL (pages 5-7)\ngases: k_ij mixing (page 8)"];
  V [label="3  c_v of every phase\nc_p - c_v identity (page 2)", fillcolor="#dbeafe"];
  W [label="4  Combine the phases\nc_p,app and c_v,app (page 9)", fillcolor="#dbeafe"];
  R [label="Result + status + calculation sheet\n(tabs 3 and 4, page 11)", fillcolor="#dcfce7"];
  D [label="Numbers come from:\nyour value > your curve > database\n(tab 2, page 10)", fillcolor="#fef9c3"];
  S -> P; P -> L; P -> G; P -> M; L -> V; G -> V; M -> V; V -> W; W -> R;
  D -> P [style=dashed, label="inputs"];
}
"""

TOPICS = [
    {
        "title": "0. Start here: how a calculation flows",
        "text": "The tool answers one question: **how much heat does a sample take up per kelvin?** The sample can be a pure fluid, "
                "a mixture, or several phases together (a liquid with solid particles, an emulsion, a slurry). Every calculation "
                "follows the same four steps.\n\n"
                "1. **Describe the sample** (tab 1): temperature, pressure, and the phases. Each phase has a state (liquid, solid, gas), "
                "a substance (a compound, or a mixture you define) and an amount.\n"
                "2. **Find c_p of every phase.** A pure liquid or solid uses data (a solid can fall back on the Debye model). A gas uses "
                "the Peng-Robinson equation of state. A mixture starts from its components and adds a correction for non-ideal mixing "
                "(Margules or NRTL for liquids, k_ij mixing for gases).\n"
                "3. **Convert to c_v** with the c_p - c_v identity, which needs the expansivity alpha_V and the compressibility kappa_T of the phase.\n"
                "4. **Combine the phases.** c_p of the sample is the mass-weighted average. c_v of the sample comes from the whole-sample "
                "identity, not from an average.\n\n"
                "Every number is looked up in a fixed order (your value, then your curve, then the database), and the result is labelled "
                "with how reliable its inputs were.\n\n"
                "**Page guide**\n\n"
                "| You want to know about | Read |\n|---|---|\n"
                "| the quantity being calculated | 1 |\n"
                "| c_v from c_p | 2 |\n"
                "| liquids and solids (data, Debye) | 3 |\n"
                "| gases (Peng-Robinson) | 4 |\n"
                "| mixtures, excess functions, Margules, NRTL, k_ij | 5, 6, 7, 8 |\n"
                "| combining phases | 9 |\n"
                "| where numbers come from, and typing your own | 10 |\n"
                "| the status of a result | 11 |\n"
                "| which model to choose | 12 |\n"
                "| symbols and units | 13 |",
        "diagram": FLOW,
        "equations": [],
        "gives": "In: T, P, phases and amounts. Out: c_p,app and c_v,app, a status, warnings, and a calculation sheet with every step.",
        "where": "Tab 1 System (describe the sample), tab 2 Data (see and override every number), tab 3 Results, tab 4 Calculation sheet.",
        "next": "Page 1.",
        "code": "engine.run_case",
    },
    {'title': '1. What is an apparent heat capacity?',
     'text': 'A sample made of several phases (a liquid with particles, an emulsion, a slurry) is heated slowly. Its apparent heat '
             'capacity is the heat taken up per kelvin and per kilogram of sample. At constant pressure it is the temperature '
             'derivative of the total enthalpy; at constant volume, of the total internal energy.',
     'equations': [('c_{p,\\mathrm{app}} \\equiv \\frac{1}{m}\\left(\\frac{\\partial H_{\\mathrm{tot}}}{\\partial '
                    'T}\\right)_P,\\qquad c_{v,\\mathrm{app}} \\equiv \\frac{1}{m}\\left(\\frac{\\partial '
                    'U_{\\mathrm{tot}}}{\\partial T}\\right)_V',
                    '(1) definitions'),
                   ('H_{\\mathrm{tot}} = \\sum_k m_k\\,h_k(T,P,\\mathbf{x}_k) + H^{\\sigma}',
                    '(1) enthalpy is additive over phases (interface separated)'),
                   ('c_{p,\\mathrm{app}} = \\sum_k w_k\\,c_{p,k},\\qquad w_k = \\frac{m_k}{m}',
                    '(2) with the interface term neglected')],
     'holds': 'slow heating; one T and one P; no melting, boiling, dissolution or reaction; interface neglected.',
     'code': 'engine.assemble, sample.cp_apparent',
     'gives': 'In: the total enthalpy (or internal energy) of the sample as a function of T. Out: heat taken up per kelvin and per '
              'kilogram.',
     'where': 'Nothing to type: this is the definition of the result shown in tab 3.',
     'next': 'Page 2 turns c_p into c_v.'},
    {'title': '2. From c_p to c_v: the calculus of thermodynamics',
     'text': 'c_p and c_v differ by the work of expansion. The triple-product rule and a Maxwell relation give the difference from '
             'the expansivity and the compressibility, which are measurable for any phase.',
     'equations': [('C_p - C_v = T\\left(\\frac{\\partial P}{\\partial T}\\right)_V\\left(\\frac{\\partial V}{\\partial T}\\right)_P '
                    '= -T\\frac{(\\partial P/\\partial T)_V^2}{(\\partial P/\\partial V)_T} = \\frac{T\\,v\\,\\alpha_V^2}{\\kappa_T}',
                    '(3)'),
                   ('c_p - c_v = \\frac{T\\,\\alpha_V^2}{\\rho\\,\\kappa_T},\\qquad \\alpha_V = \\frac{1}{V}\\left(\\frac{\\partial '
                    'V}{\\partial T}\\right)_P,\\quad \\kappa_T = -\\frac{1}{V}\\left(\\frac{\\partial V}{\\partial P}\\right)_T',
                    '(3), (12) specific form'),
                   ('\\left(\\frac{\\partial C_v}{\\partial V}\\right)_T = T\\left(\\frac{\\partial^2 P}{\\partial '
                    'T^2}\\right)_V,\\qquad \\left(\\frac{\\partial C_p}{\\partial P}\\right)_T = -T\\left(\\frac{\\partial^2 '
                    'V}{\\partial T^2}\\right)_P',
                    '(4)')],
     'holds': 'any phase of fixed composition. For water near 4 C alpha_V = 0, so c_p = c_v there.',
     'code': 'pure.cp_minus_cv, engine.cv_identity',
     'gives': 'In: c_p, T, density, alpha_V, kappa_T. Out: c_v.',
     'where': 'Tab 2 Data: rho, alpha_V and kappa_T of every phase (from the database or your value).',
     'next': 'Pages 3 and 4: how c_p of a pure phase is found.'},
    {'title': '3. Liquids and solids: data first, then the Debye model',
     'text': 'For a condensed phase c_p is taken from data (a value or a curve against T) and c_v follows from the identity of topic '
             '2. When no c_p data exist for a solid, the Debye model gives C_v from one parameter, the Debye temperature.',
     'equations': [('\\alpha_V = -\\frac{1}{\\rho}\\frac{d\\rho}{dT},\\qquad c_v = c_p - \\frac{T\\,\\alpha_V^2}{\\rho\\,\\kappa_T}',
                    '(12)'),
                   ('C_v = 9nR\\left(\\frac{T}{\\theta_D}\\right)^3\\int_0^{\\theta_D/T}\\frac{x^4e^x}{(e^x-1)^2}\\,dx + '
                    '\\gamma_eT,\\qquad C_p = C_v + \\frac{T\\,v\\,\\alpha_V^2}{\\kappa_T}',
                    '(13)'),
                   ('T \\ll \\theta_D:\\ C_v \\to \\frac{12\\pi^4}{5}nR\\left(\\frac{T}{\\theta_D}\\right)^3,\\qquad T \\gg '
                    '\\theta_D:\\ C_v \\to 3nR',
                    'limits')],
     'holds': 'data only inside their temperature range (never extrapolated). Debye: one theta_D, best for monatomic crystals.',
     'code': 'engine.m_data, engine.m_debye, pure.debye_cv',
     'gives': 'In: c_p (a value or a curve against T), rho, alpha_V, kappa_T, M; for Debye: theta_D, n, gamma_e. Out: c_p and c_v.',
     'where': 'Tab 2 Data (type under your value, or give a curve). Debye: choose method Debye in the Phases table of tab 1.',
     'next': 'Page 4 for gases, or page 5 for mixtures.'},
    {'title': '4. Gases: ideal gas plus Peng-Robinson departure',
     'text': 'A real fluid is an ideal gas plus a departure. The ideal-gas part C_p^ig(T) comes from data; the departure comes from '
             'the Peng-Robinson equation of state. The cubic in Z can have three roots: the middle one is never used, and of the '
             'outer two the one with the lower fugacity coefficient is stable.',
     'equations': [('P = \\frac{RT}{v-b} - \\frac{a(T)}{v^2+2bv-b^2},\\quad a = '
                    '0.45724\\frac{R^2T_c^2}{P_c}\\left[1+m\\left(1-\\sqrt{T/T_c}\\right)\\right]^2,\\quad b = '
                    '0.07780\\frac{RT_c}{P_c}',
                    '(6)-(7)'),
                   ('C_v = C_p^{ig} - R + C_v^R,\\qquad C_v^R = '
                    "\\frac{T\\,a''}{2\\sqrt2\\,b}\\ln\\frac{v+(1+\\sqrt2)b}{v+(1-\\sqrt2)b}",
                    '(5), (9)'),
                   ('Z^3-(1-B)Z^2+(A-3B^2-2B)Z-(AB-B^2-B^3)=0,\\quad A=\\frac{aP}{(RT)^2},\\ B=\\frac{bP}{RT}', '(10)'),
                   ('\\ln\\varphi = Z-1-\\ln(Z-B)-\\frac{A}{2\\sqrt2 B}\\ln\\frac{Z+(1+\\sqrt2)B}{Z+(1-\\sqrt2)B}',
                    '(11) choosing the stable root')],
     'holds': 'within ~1 % for vapours; only fair for liquids (C_p errors 4-26 %), poor for water and alcohols and near the critical '
              'point. For liquids the data method is used first.',
     'code': 'pure.pr_parameters, pure.pr_state, pure.select_root',
     'gives': 'In: C_p^ig(T), T_c, P_c, omega, M, T and P. Out: C_p, C_v, v, alpha_V and kappa_T of the gas.',
     'where': 'Tab 2 Data: cp_ig, Tc, Pc, omega, M. Method: auto tries Peng-Robinson first, then ideal gas.',
     'next': 'Page 5 for mixtures; page 9 to combine phases.'},
    {
        "title": "5. Mixtures (1): ideal mixing and excess functions",
        "text": "A **mixture** is one phase made of several compounds. If the components did not interact (an *ideal* mixture), "
                "the heat capacity would just be the mass-weighted average, c_p = sum of w_i c_p,i. Real mixtures differ from this. "
                "The difference is described by **excess functions**: the real value minus the ideal value at the same T, P and composition "
                "(G^E, H^E, V^E, C_p^E).\n\n"
                "The excess functions are linked by derivatives with respect to temperature: G^E gives H^E, and H^E gives C_p^E. "
                "So one model for G^E is enough to get the correction to c_p. Two models are provided for liquid mixtures of two components: "
                "**Margules** (page 6) and **NRTL** (page 7). Gas mixtures use Peng-Robinson mixing (page 8).\n\n"
                "You may give the composition as mole, mass or volume fractions (the volume the pure components had before mixing). "
                "They are converted to mass fractions with the molar masses and densities.",
        "equations": [
            (r"w_i = \frac{x_iM_i}{\sum_j x_jM_j}", "mole fractions to mass fractions"),
            (r"c_p = \sum_i w_i\,c_{p,i} + \frac{C_p^E}{M},\qquad C_p^E = -T\left(\frac{\partial^2G^E}{\partial T^2}\right)_{P,x},"
             r"\quad H^E = -T^2\frac{\partial(G^E/T)}{\partial T}", "(14)"),
            (r"c_p - c_v = \frac{T\left(\sum_i w_i\alpha_i/\rho_i\right)^2}{\sum_i w_i\kappa_i/\rho_i}\quad(V^E = 0)", "(19) c_v of a mixture"),
        ],
        "holds": "Margules and NRTL: two components. Model auto = NRTL or Margules if their parameters are given, otherwise ideal "
                 "(C_p^E = 0, listed as an assumption). The density, alpha_V and kappa_T of a mixture assume V^E = 0.",
        "gives": "In: components, fractions, basis, model, pair parameters. Out: c_p and c_v of the mixture.",
        "where": "Tab 1 System, Mixtures section: components, fraction basis and model.",
        "next": "Page 6 (Margules) or page 7 (NRTL).",
        "code": "engine.mix_condensed, mixtures.py",
    },
    {
        "title": "6. Mixtures (2): the Margules model",
        "text": "Margules is the simplest model for G^E of a liquid with two components: one expression with three constants, A, B and D. "
                "Each constant has a job. **A** sets the size of G^E and does not depend on T. **B** gives the excess enthalpy H^E. "
                "**D** gives the excess heat capacity C_p^E.\n\n"
                "What this means in practice:\n\n"
                "- with B = D = 0 (only A), H^E = 0 and C_p^E = 0: the mixture behaves ideally in heat terms;\n"
                "- with D = 0 (A and B), H^E is a constant and still C_p^E = 0;\n"
                "- a non-zero C_p^E needs D different from 0. D is always required in the program: type 0 if you accept C_p^E = 0.\n\n"
                "Use Margules when you have measured H^E or C_p^E data to fit B and D. The activity coefficients of this symmetric form "
                "are also given below for reference; the program does not need them.",
        "equations": [
            (r"\frac{G^E}{RT} = x_1x_2\left(A+\frac{B}{T}+D\ln T\right)", "(15) the model, T in K"),
            (r"H^E = Rx_1x_2\,(B-DT),\qquad C_p^E = -RD\,x_1x_2", "(15) what follows from it"),
            (r"\ln\gamma_1 = x_2^2\left(A+\frac{B}{T}+D\ln T\right),\qquad \ln\gamma_2 = x_1^2\left(A+\frac{B}{T}+D\ln T\right)", "activity coefficients (for reference)"),
        ],
        "holds": "Two components; one composition-independent coefficient (symmetric mixtures). Fit B and D to H^E or C_p^E data for good caloric results.",
        "gives": "In: A, B, D (symmetric: the order of the two compounds does not matter). Out: H^E, C_p^E and the corrected c_p.",
        "where": "Tab 1 System, Advanced section: choose Margules. Or the pair-parameter table: rows marg_A, marg_B, marg_D.",
        "next": "Page 7 for the NRTL model, page 9 to combine phases.",
        "code": "mixtures.ge_margules, margules_he, margules_cpe",
    },
    {
        "title": "7. Mixtures (3): the NRTL model",
        "text": "NRTL (Non-Random Two-Liquid) is a local-composition model. Around a molecule of component 1 the composition is not the "
                "overall composition (hydrogen bonding, for example, makes unlike molecules cluster differently). The model captures this with "
                "two interaction terms, **tau_12** and **tau_21**, and a non-randomness constant **alpha** (usually 0.2 to 0.5, often fixed at 0.3). "
                "The terms are **not symmetric**: tau_12 (1 to 2) differs from tau_21 (2 to 1), so the order matters.\n\n"
                "Each tau can depend on temperature through three numbers, a, b and e. Many sources give tau = A/T: then type A in **b** "
                "and leave a and e at 0. If a source gives an energy difference tau = delta g / (R T), then b = delta g / R (R = 8.314 J/mol/K).\n\n"
                "How the program uses it: it evaluates G^E at T minus and plus 0.01 K and differentiates numerically to get H^E and C_p^E (Eq. 14). "
                "The activity coefficients are not needed for c_p, but they are the usual test that parameters were entered correctly, so the "
                "Advanced panel prints tau, G and the infinite-dilution activity coefficients.\n\n"
                "**Worked example** (illustrative values for ethanol (1) + water (2) at 298.15 K: A_12 = 3.17 K, A_21 = 523.84 K, alpha = 0.30). "
                "Then tau_12 = 0.01063, tau_21 = 1.757, G_12 = 0.9968, G_21 = 0.5903, and at infinite dilution gamma_1 = 5.86 "
                "(ethanol in water) and gamma_2 = 2.85 (water in ethanol).\n\n"
                "**Two things to remember.** (1) If tau does not depend on T (only a is given), then H^E = 0 and C_p^E = 0: the temperature "
                "dependence (b and e) is what creates the caloric corrections. (2) Parameters fitted to vapour-liquid equilibrium describe G^E and the "
                "activity coefficients well, but their temperature derivatives (H^E, C_p^E) can be poor. Prefer parameters fitted to H^E or C_p^E data.",
        "equations": [
            (r"\frac{G^E}{RT} = x_1x_2\left[\frac{\tau_{21}G_{21}}{x_1+x_2G_{21}}+\frac{\tau_{12}G_{12}}{x_2+x_1G_{12}}\right]", "(16) the model"),
            (r"G_{ij}=e^{-\alpha\tau_{ij}},\qquad \tau_{ij}=a_{ij}+\frac{b_{ij}}{T}+e_{ij}\ln T", "(16) tau and G (T in K)"),
            (r"\ln\gamma_1 = x_2^2\left[\tau_{21}\left(\frac{G_{21}}{x_1+x_2G_{21}}\right)^2+\frac{\tau_{12}G_{12}}{(x_2+x_1G_{12})^2}\right]", "activity coefficient of 1 (for reference)"),
            (r"\ln\gamma_2 = x_1^2\left[\tau_{12}\left(\frac{G_{12}}{x_2+x_1G_{12}}\right)^2+\frac{\tau_{21}G_{21}}{(x_1+x_2G_{21})^2}\right]", "activity coefficient of 2 (for reference)"),
            (r"\ln\gamma_1^{\infty} = \tau_{21}+\tau_{12}G_{12},\qquad \ln\gamma_2^{\infty} = \tau_{12}+\tau_{21}G_{21}", "infinite dilution: a quick check of the inputs"),
        ],
        "holds": "Two components. The reference states are the pure liquids at the same T and P. Parameters must be in the same form as the equations above (tau in K divided by T, or a, b, e).",
        "gives": "In: alpha and tau_12, tau_21 (a, b, e each). Out: G^E(T), then H^E, C_p^E and the corrected c_p.",
        "where": "Tab 1 System, Advanced section: choose NRTL, fill the boxes, press Apply. Or the pair-parameter table: nrtl_a, nrtl_b, nrtl_e for each ordered pair, and nrtl_alpha.",
        "next": "Page 8 for gas mixtures, page 9 to combine phases.",
        "code": "mixtures.ge_nrtl, he_from_ge, nrtl_summary",
    },
    {
        "title": "8. Mixtures (4): gas mixtures and k_ij",
        "text": "A gas mixture is treated as one Peng-Robinson fluid whose constants a and b are built from those of the pure gases "
                "(van der Waals one-fluid mixing). The binary interaction parameter **k_ij** corrects the cross term between unlike molecules. "
                "It is small (typically 0 to 0.1) and 0 means no correction. If it is blank the program uses 0, lists this as an assumption "
                "and lowers the status of the result. The departure functions of page 4 are then applied with the mixture constants.\n\n"
                "The simpler alternative is the *ideal gas* model: the mixture C_p is the mole-fraction average of the pure-gas C_p^ig.",
        "equations": [
            (r"a_m = \sum_i\sum_j x_ix_j(1-k_{ij})\sqrt{a_ia_j},\qquad b_m = \sum_i x_ib_i", "(17) mixing rules"),
            (r"C_p^{ig,\,\mathrm{mix}} = \sum_i x_i\,C_{p,i}^{ig}", "ideal-gas mixture"),
        ],
        "holds": "Needs T_c, P_c and omega for every component. k_ij is symmetric (k_ij = k_ji) and the same at all T in this program.",
        "gives": "In: T_c, P_c, omega, C_p^ig of each gas, optional k_ij. Out: C_p, C_v and density of the gas mixture.",
        "where": "Tab 1 System, Advanced section: choose Peng-Robinson k_ij. Or the pair-parameter table: row kij.",
        "next": "Page 9 to combine phases.",
        "code": "engine.mix_peng_robinson, mixtures.mix_pr",
    },
    {'title': '9. The whole sample: c_p and c_v',
     'text': 'Phase volume fractions become mass fractions through the densities. c_p of the sample is the mass average '
             '(thermal-equilibrium model). c_v is NOT the mass average of the phase c_v: at constant total volume the phases push on '
             'each other. The whole-sample identity gives it exactly, and the mass average is only a lower bound.',
     'equations': [('w_k = \\frac{\\phi_k\\rho_k}{\\sum_j\\phi_j\\rho_j},\\qquad c_{p,\\mathrm{app}} = \\sum_k w_k\\,c_{p,k} = '
                    '\\frac{\\sum_k\\phi_k(\\rho c_p)_k}{\\rho_s}',
                    '(20)'),
                   ('c_{p,\\mathrm{app}} - c_{v,\\mathrm{app}} = '
                    '\\frac{T\\left(\\sum_k\\phi_k\\alpha_k\\right)^2}{\\rho_s\\sum_k\\phi_k\\kappa_k}',
                    '(21)'),
                   ('c_{v,\\mathrm{app}} - \\sum_k w_kc_{v,k} = '
                    '\\frac{T}{\\rho_s\\sum_j\\phi_j\\kappa_j}\\sum_{k<l}\\phi_k\\phi_l\\kappa_k\\kappa_l\\left(\\frac{\\alpha_k}{\\kappa_k}-\\frac{\\alpha_l}{\\kappa_l}\\right)^2 '
                    '\\geq 0',
                    '(22)-(23)'),
                   ('c_p^{\\mathrm{Pak\\text{-}Cho}} = \\sum_k\\phi_k\\,c_{p,k}\\quad\\text{(diagnostic only: weights a per-mass '
                    'quantity by volume)}',
                    'Pak-Cho form')],
     'holds': 'needs rho of every phase (for volume fractions) and alpha_V, kappa_T of every phase (for c_v).',
     'code': 'engine.assemble, sample.py',
     'gives': 'In: c_p, rho, alpha_V, kappa_T and the volume (or mass) fraction of every phase. Out: c_p,app and c_v,app of the '
              'sample.',
     'where': 'Tab 1 System: the amounts in the Phases table (volume or mass fractions, they must sum to 1).',
     'next': 'Page 10: where each number comes from.'},
    {
        "title": "10. Where the numbers come from (and typing your own)",
        "text": "For every property the program takes, in this order: **your value** (if valid at T), your curve, the database value, the "
                "database curve, then a derivation (alpha_V from a density curve). **Anything you type always wins.** Nothing is extrapolated: "
                "outside a data range the run stops and says which range exists. If a method lacks inputs, the next method is tried; if none works, "
                "one message lists what each method needs.\n\n"
                "There are three ways to give your own numbers:\n\n"
                "- **Tab 2 Data, column *your value*:** a single compound property (molar mass, density, c_p, alpha_V, kappa_T, T_c, P_c, omega, ...). "
                "Choose the unit, an optional valid temperature range, the kind of data and a source.\n"
                "- **Tab 2 Data, temperature curves:** several (T, value) points. They are interpolated linearly and never extrapolated.\n"
                "- **Tab 1, Advanced section:** parameters of a mixture model (NRTL, Margules, k_ij), which describe a *pair* of compounds, not one.",
        "equations": [],
        "holds": "The database holds CoolProp reference equations (about 130 fluids), thermo/chemicals evaluated data (Zabransky, DIPPR, VDI, NIST-JANAF, "
                 "NIST WebBook, Perry, CRC) and the spec values. Liquid data are at 1 atm.",
        "gives": "In: whatever you type, plus the database. Out: one value per property at T, with its source and kind.",
        "where": "Tab 2 Data shows, for each compound and property, the value in use, its status, the database value and your value.",
        "next": "Page 11: how reliable the result is.",
        "code": "properties.find",
    },
    {'title': '11. Evidence and status',
     'text': 'Each number carries its kind: experimental (measured or evaluated data), derived (computed from such data), '
             'unspecified, estimated (an estimation method), illustrative (a placeholder). A result is only as strong as its weakest '
             'input. Status: calculated; calculated under assumptions (an assumption, a warning or weaker data were used: all are '
             'listed); not calculable (nothing is printed).',
     'equations': [],
     'holds': 'assumptions the program may make (always listed): C_p^E = 0 for an ideal mixture, V^E = 0 for mixture volumes, k_ij = '
              '0 when blank, gamma_e = 0 when blank, a value without a T range used at any T.',
     'code': 'engine.build_result',
     'gives': 'In: the kind of every input. Out: the status of the result and the list of assumptions and warnings.',
     'where': 'Tab 3 Results (status, warnings, assumptions) and the provenance list.',
     'next': 'Page 12: choosing a model.'},
    {
        "title": "12. Which model should I choose?",
        "text": "Leave the method on **auto** unless you have a reason; the table shows what auto does and what each choice needs.\n\n"
                "| Situation | Model | What you provide |\n|---|---|---|\n"
                "| pure liquid | data (auto) | c_p, rho, alpha_V, kappa_T, M: in the database for 192 compounds |\n"
                "| pure solid with c_p known | data (auto) | same as a liquid |\n"
                "| pure solid, no c_p | Debye (auto falls back to it) | theta_D, n, gamma_e, plus rho, alpha_V, kappa_T, M |\n"
                "| pure gas | Peng-Robinson, then ideal gas (auto) | T_c, P_c, omega, C_p^ig, M |\n"
                "| liquid mixture, no parameters | ideal (auto) | nothing: C_p^E = 0 is assumed and listed |\n"
                "| liquid mixture, H^E or C_p^E data | Margules | A, B, D |\n"
                "| liquid mixture, activity-coefficient parameters | NRTL | alpha and tau_12, tau_21 (a, b, e) |\n"
                "| gas mixture | Peng-Robinson, or ideal gas | T_c, P_c, omega per gas; k_ij optional |\n\n"
                "Peng-Robinson for a **liquid** is available only if you choose it: its caloric errors reach about 26 %, so the data method is preferred.",
        "equations": [],
        "gives": "A decision aid; no calculation.",
        "where": "Tab 1 System: the method column of the Phases table and the model box of each mixture.",
        "next": "Page 13: symbols.",
        "code": "constants.AUTO_PURE, MIX_MODELS",
    },
    {
        "title": "13. Symbols and units",
        "text": "The program works in SI units internally (K, Pa, kg, J, mol). In the tables you may choose another unit and it is converted once.\n\n"
                "| Symbol | Meaning | SI unit |\n|---|---|---|\n"
                "| T, P | temperature, pressure | K, Pa |\n"
                "| x_i, w_i, phi_i | mole, mass and volume fraction | - |\n"
                "| M | molar mass | kg/mol |\n"
                "| rho | density | kg/m3 |\n"
                "| c_p, c_v | specific heat capacity (per kg) | J/kg/K |\n"
                "| C_p, C_v | molar heat capacity (per mol) | J/mol/K |\n"
                "| alpha_V | volume expansivity | 1/K |\n"
                "| kappa_T | isothermal compressibility | 1/Pa |\n"
                "| G^E, H^E, V^E, C_p^E | excess Gibbs energy, enthalpy, volume, heat capacity | J/mol, J/mol, m3/mol, J/mol/K |\n"
                "| gamma_i | activity coefficient of component i | - |\n"
                "| tau_ij, G_ij, alpha | NRTL interaction terms and non-randomness constant | -, -, - |\n"
                "| a_ij, b_ij, e_ij | NRTL temperature coefficients: tau = a + b/T + e ln T | -, K, - |\n"
                "| A, B, D | Margules constants | -, K, - |\n"
                "| k_ij | Peng-Robinson binary interaction parameter | - |\n"
                "| T_c, P_c, omega | critical temperature, critical pressure, acentric factor | K, Pa, - |\n"
                "| theta_D, n, gamma_e | Debye temperature, atoms per formula unit, electronic coefficient | K, -, J/mol/K2 |\n"
                "| R | gas constant, 8.314 J/mol/K | J/mol/K |\n\n"
                "Do not confuse **gamma_i** (activity coefficient of a mixture component) with **gamma_e** (electronic heat-capacity coefficient of a metal).",
        "equations": [],
        "gives": "A reference; no calculation.",
        "where": "The same names appear in the Data and Pair-parameter tables.",
        "code": "constants.PROPS, constants.PAIR_KEYS",
    },
]

