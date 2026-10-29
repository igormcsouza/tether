# Plan to Convert shop/cli.py into Subcommands

1. **Design the Subcommand Structure**
   - Define a registry to hold subcommand functions.
   - Each subcommand will be a function that takes arguments and performs a specific task.
   - The registry will map subcommand names to their corresponding functions.

2. **Create a Base Function for Subcommands**
   - Implement a base function that parses the command line arguments and invokes the appropriate subcommand function from the registry.
   - The base function should handle common arguments and pass the rest to the subcommand function.

3. **Refactor Existing Commands**
   - Identify the existing command, `summary`, and refactor it into a subcommand function.
   - Ensure that the refactored function can be invoked through the base function.

4. **Add Subcommands**
   - Implement additional subcommands such as `export` and others as needed.
   - Each subcommand should be a function that performs a specific task and can be invoked through the base function.

5. **Registry Management**
   - Create a registry that maps subcommand names to their corresponding functions.
   - Ensure that the registry is initialized with the existing subcommands and can be extended with new ones.

6. **Report Formats**
   - Design a system for adding report formats without editing the CLI.
   - Each report format should be a function that takes the data and returns a formatted string.
   - The subcommand functions should be able to use different report formats based on user input or configuration.

7. **Testing and Verification**
   - Write unit tests for each subcommand function to ensure they work as expected.
   - Test the base function to ensure it correctly invokes the appropriate subcommand function.
   - Verify that existing `summary` invocations continue to work as expected.
   - Test the new subcommands to ensure they perform the expected tasks.
   - Verify that the report formats can be added and used without editing the CLI.

8. **Documentation**
   - Update the documentation to reflect the new subcommand structure and report format system.
   - Provide examples of how to use the new subcommands and report formats.

9. **Deployment**
   - Deploy the changes to the production environment.
   - Monitor the system to ensure that the new subcommands and report formats are working as expected.
   - Address any issues that arise during deployment.