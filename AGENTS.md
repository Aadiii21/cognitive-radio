# LOCAL-FIRST EXECUTION RULES

1. Execute shell commands directly using the terminal.
2. Never delegate simple file operations, CSV inspection,
   Python execution, testing, Git operations, or plotting
   to another AI agent or external API.
3. Batch related shell commands into a single execution.
4. Never repeatedly retry HTTP 429 responses.
5. On HTTP 429, stop using that provider for the current task
   and use the configured fallback if available.
6. Continue independent work without waiting for remote services.
7. Use local Python libraries for data analysis and visualization.
8. Do not install unnecessary dependencies.
9. Preserve existing work and create checkpoints before
   destructive modifications.
10. Run tests and verify outputs before reporting success.
11. Maintain results/final/execution_log.md as a local
    progress and recovery record.
12. Do not expand project scope.
13. Do not enable physical RF transmission automatically.
14. Never fabricate experimental results or hardware validation.
15. Complete implementation, testing, documentation,
    plots, and presentation preparation.
    
    DEPENDENCY MANAGEMENT:
- Always inspect the active Python interpreter before installing packages.
- Prefer the existing cognitive-radio conda environment.
- Check whether dependencies are already installed before installing.
- Never install packages globally on Arch Linux.
- Never install packages unnecessarily.
- Use set -o pipefail when piping command output.
- Verify imports after installation.
- Never interpret a successful tail command as proof that installation succeeded.




## PYTHON ENVIRONMENT

- Project environment: existing cognitive-radio Conda environment.
- Interpreter: inspect `which python` before execution.
- Never use system Python for package installation.
- Never use `sudo pip`.
- Never recreate or delete the existing environment.
- Prefer existing installed packages.
- Verify every installation with an import test.
