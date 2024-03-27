# Blank

This directory contains an empty pi-base project - a template for creating new projects.

## Instructions

1. Choose a name for the new project (lowercase, underscores, no spaces). In all instructions below replace \<name\> with your project name, for the code examples use `${proj}` (run commands in the root workspace folder):

    ```bash
    export proj=<name>
    ```

2. Create a new git branch for staging the new project:

    ```bash
    git checkout -b ${proj}
    git push origin ${proj}
    ```

3. Copy whole "blank" folder to "\<name\>" and rename "blank.py" in the result to "\<name\>.py"".

   ```bash
   cp -Rv blank ${proj}
   mv ${proj}/blank.py ${proj}/${proj}.py
   ```

4. Edit "\<name\>/conf.yaml" file to change "blank" to "\<name\>"

    ```bash
    sed -i ${proj}/conf.yaml -re "s/blank/${proj}/g"
    ```

5. Edit Info > Name field in "\<name\>/conf.yaml" file to describe what the new project is intended to do.

6. Add "\<name\>" project files to git:

    ```bash
    git add ${proj}/*
    git commit -m "Created "${proj}" project"
    git push
    ```
  
7. Setup is Done! Now add functionality to "\<name\>/\<name\>.py" file.
