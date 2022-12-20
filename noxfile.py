# noxfile.py
import nox


@nox.session(python=["3.10", "3.11"])
def tests(session):

    session.run("poetry", "install", "--only", "main", external=True)
    session.run("pytest", "-m", "short")
