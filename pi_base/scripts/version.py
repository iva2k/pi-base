import os


def prerelease_middle(data: dict) -> None:
    # print("DEBUG: got into prerelase_middle()")
    # print("\n".join(f"{k}\t{v}" for k, v in data.items()))
    filename = os.path.join(data["reporoot"], "pi_base", "common", "common_requirements.txt")
    package = "pi_base"
    with open(filename, encoding="utf-8") as fd:
        lines = fd.readlines()

    new_version = data["new_version"]
    modified = []
    with open(filename, "w", encoding="utf-8") as fd:
        for line_in in lines:
            line_out = line_in
            for op in [">=", "~=", "=="]:
                if line_in.startswith(f"{package}{op}"):
                    line_out = f"{package}{op}{new_version}\n"
                    modified.append((line_in.strip("\n"), line_out.strip("\n")))
                    break
            fd.write(line_out)
    print(f'Modified file "{filename}", changed package "{package}" version:')
    for m in modified:
        a, b = m
        print(f"  - {a}")
        print(f"  + {b}")
        print("")
