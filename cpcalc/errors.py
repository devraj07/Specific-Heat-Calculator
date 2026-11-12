"""The one exception class. A CalcError carries a list of problems so that every
problem of a case is reported at once."""


class CalcError(Exception):
    def __init__(self, problems):
        if isinstance(problems, dict):
            problems = [problems]
        self.problems = problems
        self.code = problems[0]["code"] if problems else "E01"
        super().__init__("; ".join("%s %s" % (p["code"], p["what"]) for p in problems))


def problem(code, what, fix="", lines=None, affects=("cp", "cv")):
    """One problem: code, what went wrong, how to fix it, extra detail lines."""
    return {"code": code, "what": what, "fix": fix, "lines": list(lines or []), "affects": list(affects)}
