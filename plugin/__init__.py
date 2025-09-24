from pathlib import Path
from typing import Dict, List


class BaseUploader:
    """Base class for upload plugins with common functionality.

    This class handles common tasks like file organization, validation, and metadata
    that are shared across all upload plugins. Plugin developers should inherit
    from this class and implement the required methods for their specific logic.

    Core Methods:
        handle_upload_files(): Main upload method - handles the complete upload workflow
        organize_files(): Handle file organization logic (can be overridden)
        validate_files(): Handle file validation logic (can be overridden)

    Required Methods (should be implemented by subclasses):
        process_files(): Transform/process files during upload

    Optional Methods (can be overridden by subclasses):
        before_process(): Pre-process files before main processing
        after_process(): Post-process files after main processing
        setup_directories(): Setup custom directories
        validate_file_types(): Custom file type validation

    Helper Methods:
        _log_validation_warning(): Log validation warnings
        _log_conversion_warning(): Log conversion warnings
        _filter_valid_files(): Filter files based on validation

    Auto-provided Utilities:
        Logging via self.run.log_message() and other run methods
        File path utilities via self.path
        Specification access via self.file_specification
    """

    def __init__(
        self,
        run,
        path: Path,
        file_specification: List = None,
        organized_files: List = None,
        extra_params: Dict = None,
    ):
        """Initialize the base upload class.

        Args:
            run: Plugin run object with logging capabilities.
            path: Path object pointing to the upload target directory.
            file_specification: List of specifications that define the structure of files to be uploaded.
            organized_files: List of pre-organized files based on the default logic.
            extra_params: Additional parameters for customization.
        """
        self.run = run
        self.path = path
        self.file_specification = file_specification or []
        self.organized_files = organized_files or []
        self.extra_params = extra_params or {}

    def _log_validation_warning(self, spec_name: str, invalid_extensions: List[str], expected_extensions: List[str]):
        """Log validation warning for invalid file extensions."""
        self.run.log_message(
            f"Validation warning in '{spec_name}': File extensions {invalid_extensions} do not match expected extensions {expected_extensions}. These files will be excluded from upload."
        )

    def _log_conversion_warning(self, spec_name: str, extension: str, recommended_formats: str):
        """Log conversion warning for file formats that may need conversion."""
        self.run.log_message(
            f"Conversion warning in '{spec_name}': File extension '{extension}' may require conversion to [{recommended_formats}]."
        )

    def _filter_valid_files(self, files_to_validate: List) -> List:
        """Filter files based on validation criteria.

        Args:
            files_to_validate: List of organized file dictionaries to validate

        Returns:
            List: Filtered list containing only valid files
        """
        return files_to_validate  # Default: return all files

    def get_file_extensions_config(self) -> Dict[str, List[str]]:
        """Get allowed file extensions configuration.

        Returns:
            Dict mapping file categories to allowed extensions
        """
        return {
            'pcd': ['.pcd'],
            'text': ['.txt', '.html'],
            'audio': ['.wav', '.mp3'],
            'data': ['.bin', '.json', '.fbx'],
            'image': ['.jpg', '.jpeg', '.png'],
            'video': ['.mp4'],
        }

    def get_conversion_warnings_config(self) -> Dict[str, str]:
        """Get file conversion warnings configuration.

        Returns:
            Dict mapping problematic extensions to recommended formats
        """
        return {
            '.tif': ' .jpg, .png',
            '.tiff': ' .jpg, .png',
            '.avi': ' .mp4',
            '.mov': ' .mp4',
            '.mkv': ' .mp4',
            '.wmv': ' .mp4',
        }

    # Abstract methods that should be implemented by subclasses
    def process_files(self, organized_files: List) -> List:
        """Process files. Should be implemented by subclasses."""
        return organized_files

    def before_process(self, organized_files: List) -> List:
        """Pre-process files before main processing. Can be overridden by subclasses."""
        return organized_files

    def after_process(self, processed_files: List) -> List:
        """Post-process files after main processing. Can be overridden by subclasses."""
        return processed_files

    def organize_files(self, files: List) -> List:
        """Organize files. Can be overridden by subclasses."""
        return files

    def validate_files(self, files: List) -> List:
        """Validate files. Can be overridden by subclasses."""
        return self._filter_valid_files(files)

    def setup_directories(self) -> None:
        """Setup custom directories. Can be overridden by subclasses."""
        pass

    def validate_file_types(self, organized_files: List) -> List:
        """Validate file types against specifications with comprehensive filtering logic.

        This method implements the complete validation logic from legacy code,
        filtering out files that don't match their expected specifications.

        Args:
            organized_files: List of organized file dictionaries

        Returns:
            List: Filtered list containing only valid files that match specifications
        """
        if not organized_files or not self.file_specification:
            return organized_files

        valid_files = []
        allowed_extensions = self.get_file_extensions_config()
        conversion_warnings = self.get_conversion_warnings_config()
        warning_extensions = list(conversion_warnings.keys())
        all_violation_case = {}

        for file_group in organized_files:
            files_dict = file_group.get('files', {})
            invalid_case = {}
            warning_case = {}

            for spec_name, file_path in files_dict.items():
                # Find the specification for this file type
                file_spec = next((s for s in self.file_specification if s['name'] == spec_name), None)
                if not file_spec:
                    continue

                # Handle file path lists
                if isinstance(file_path, list):
                    file_path = file_path[0] if len(file_path) == 1 else file_path

                # Extract file information
                file_category = spec_name.split('_')[0]
                file_type = file_spec['file_type']
                file_extension = file_path.suffix.lower()

                # Check if file needs conversion warning (these files will be excluded)
                if file_extension in warning_extensions:
                    case = invalid_case.get(spec_name, {})
                    case['warning'] = case.get('warning', []) + [file_extension]
                    warning_case[spec_name] = case
                    break

                # Validate against file category (e.g., 'image', 'data', etc.)
                if file_category in allowed_extensions.keys():
                    if file_extension in allowed_extensions[file_category]:
                        continue  # Valid file
                    else:
                        case = invalid_case.get(spec_name, {})
                        case['invalid'] = case.get('invalid', []) + [file_extension]
                        case['expected'] = allowed_extensions[file_category]
                        invalid_case[spec_name] = case
                        break

                # Validate against file type from specification
                if file_type in allowed_extensions.keys():
                    if file_extension in allowed_extensions[file_type]:
                        continue  # Valid file
                    else:
                        case = invalid_case.get(spec_name, {})
                        case['invalid'] = case.get('invalid', []) + [file_extension]
                        case['expected'] = allowed_extensions[file_type]
                        invalid_case[spec_name] = case
                        break

            # If violations found, exclude this file group
            if invalid_case or warning_case:
                all_violation_case[spec_name] = {
                    'invalid': invalid_case.get(spec_name, {}),
                    'warning': warning_case.get(spec_name, {}),
                }
                continue  # Skip this file group

            # No violations - add to valid files
            valid_files.append(file_group)

        # Log all violations found during validation
        self._log_all_violations(all_violation_case, conversion_warnings)

        return valid_files

    def _log_all_violations(self, all_violation_case: Dict, conversion_warnings: Dict):
        """Log all validation violations found during file validation."""
        for spec_name, violation_info in all_violation_case.items():
            if violation_info['invalid']:
                self.run.log_message(
                    f"Validation warning in '{spec_name}': File extensions {violation_info['invalid']['invalid']} do not match expected extensions {violation_info['invalid']['expected']}. These files will be excluded from upload."
                )
            if violation_info['warning']:
                for warning in violation_info['warning']['warning']:
                    if warning in conversion_warnings:
                        self.run.log_message(
                            f"Conversion warning in '{spec_name}': File extension '{warning}' may require conversion to [{conversion_warnings[warning]}]."
                        )

    def handle_upload_files(self) -> List:
        """Main upload method that handles the complete upload workflow.

        This method provides the core workflow for upload plugins:
        setup_directories -> organize_files -> before_process -> process_files ->
        after_process -> validate_files

        Returns:
            List: The final processed and validated list of files ready for upload.
        """
        # Setup any required directories
        self.setup_directories()

        # Start with organized files from the workflow
        current_files = self.organized_files

        # Apply organization logic
        current_files = self.organize_files(current_files)

        # Pre-process files
        current_files = self.before_process(current_files)

        # Main processing step
        current_files = self.process_files(current_files)

        # Post-process files
        current_files = self.after_process(current_files)

        # Final validation
        current_files = self.validate_files(current_files)

        return current_files
