#include <unistd.h>
#include <libgen.h>
#include <limits.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <mach-o/dyld.h>

int main(int argc, char *argv[]) {
    char path[PATH_MAX];
    uint32_t size = sizeof(path);
    if (_NSGetExecutablePath(path, &size) != 0) {
        return 1;
    }
    char resolved[PATH_MAX];
    if (realpath(path, resolved) == NULL) {
        strncpy(resolved, path, sizeof(resolved) - 1);
    }
    char *dir = dirname(resolved);
    char resource_dir[PATH_MAX];
    snprintf(resource_dir, sizeof(resource_dir), "%s/../Resources", dir);
    char script_path[PATH_MAX];
    snprintf(script_path, sizeof(script_path), "%s/helper.py", resource_dir);
    
    char pythonpath[PATH_MAX * 2];
    snprintf(pythonpath, sizeof(pythonpath), "PYTHONPATH=%s", resource_dir);
    putenv(pythonpath);
    
    // Pick the best python3 binary that has user dependencies (pyautogui, PIL)
    const char *candidates[] = {
        "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
        "/usr/local/bin/python3",
        "/opt/homebrew/bin/python3",
        "/usr/bin/python3",
        NULL
    };
    const char *python_bin = "/usr/bin/python3";
    for (int i = 0; candidates[i] != NULL; i++) {
        if (access(candidates[i], X_OK) == 0) {
            python_bin = candidates[i];
            break;
        }
    }
    
    // Launch python directly as an arm64 process (native execution, no arch wrapper)
    char **new_argv = malloc((argc + 3) * sizeof(char *));
    new_argv[0] = (char *)python_bin;
    new_argv[1] = script_path;
    for (int i = 1; i < argc; i++) {
        new_argv[i + 1] = argv[i];
    }
    new_argv[argc + 1] = NULL;
    
    execv(python_bin, new_argv);
    perror("execv failed");
    return 1;
}
