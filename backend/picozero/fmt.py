# backend/picozero/fmt.py
# Números e datas no padrão brasileiro para os textos gerados pelas regras.


def inteiro(n: float) -> str:
    return f"{round(n):,}".replace(",", ".")


def decimal(x: float, casas: int = 1) -> str:
    return f"{x:.{casas}f}".replace(".", ",")


def ddmm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def ddmmaaaa(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"
