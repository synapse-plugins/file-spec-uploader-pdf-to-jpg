from pathlib import Path
from typing import Dict, List


class ValidationError(Exception):
    """Exception raised when files don't match their directory specifications."""

    def __init__(self, directory: str, invalid_files: List[str], expected_extensions: List[str]):
        self.directory = directory
        self.invalid_files = invalid_files
        self.expected_extensions = expected_extensions
        super().__init__(
            f"Validation error in '{directory}': Files {invalid_files} do not match expected extensions {expected_extensions}"
        )


class FileTypeMismatchError(Exception):
    """Exception raised when file types don't match their specifications."""

    def __init__(self, file_path: Path, expected_type: str, actual_type: str):
        self.file_path = file_path
        self.expected_type = expected_type
        self.actual_type = actual_type
        super().__init__(
            f"Error: File type mismatch for '{file_path.name}' - expected '{expected_type}' but found '{actual_type}'"
        )


class Uploader:
    """Plugin upload action interface for organizing files.

    This class provides a minimal interface for plugin developers to implement
    their own file organization logic.
    """

    def __init__(
        self, run, path: Path, file_specification: List = None, organized_files: List = None, extra_params: Dict = None
    ):
        """Initialize the plugin upload action class.

        Args:
            run: Plugin run object with logging capabilities.
            path: Path object pointing to the upload target directory.
            file_specification: List of specifications that define the structure of files to be uploaded.
                Each specification contains details like file name, type, and requirements.
            organized_files: List of pre-organized files based on the default logic.
                Each item is a dictionary with 'files' and 'meta' keys.
            extra_params: Additional parameters for customization.
        """
        self.run = run
        self.path = path
        self.file_specification = file_specification
        self.organized_files = organized_files
        self.extra_params = extra_params

    def handle_upload_files(self) -> List:
        """Customize the organization of files for upload.

        This method provides a hook for plugin developers to modify the default file organization.
        You can override this method to filter files, transform data, or add custom metadata
        based on your specific requirements.

        Args:
            organized_files (List): The default organized files structure.
                Each item is a dictionary with 'files' and 'meta' keys.

        Returns:
            List: The modified list of organized files to be uploaded.
        """
        # Validate file types against specifications and raise exception if mismatch
        if self.organized_files and self.file_specification:
            validated_files = self.validate_file_types(self.organized_files)
            return validated_files
        else:
            return self.organized_files or []

    def validate_file_types(self, organized_files: List) -> List:
        """Validate file types match their expected specifications based on directory patterns.

        Args:
            organized_files (List): List of organized file dictionaries.

        Returns:
            List: Filtered list with only valid files.

        Raises:
            ValidationError: When files don't match expected extensions for their directory type.
        """
        valid_files = []

        # Define allowed extensions for each file type
        allowed_extensions = {
            'pcd': ['.pcd'],
            'text': ['.txt', '.html'],
            'audio': ['.wav', '.mp3'],
            'data': ['.bin', '.json', '.fbx'],
            'image': ['.jpg', '.jpeg', '.png'],
            'video': ['.mp4'],
        }

        # Extensions that require conversion warnings
        warning_extensions = ['.tif', '.tiff'] + ['.avi', '.mov', '.mkv', '.wmv']
        conversion_warnings = {
            '.tif': ' .jpg, .png',
            '.tiff': ' .jpg, .png',
            '.avi': ' .mp4',
            '.mov': ' .mp4',
            '.mkv': ' .mp4',
            '.wmv': ' .mp4',
        }
        all_violation_case = {}

        for file_group in organized_files:
            files_dict = file_group.get('files', {})
            invalid_case = {}
            warning_case = {}
            for spec_name, file_path in files_dict.items():
                # Find the specification for this file type
                file_spec = next((s for s in self.file_specification if s['name'] == spec_name), None)
                if isinstance(file_path, list):
                    file_path = file_path[0] if len(file_path) == 1 else file_path

                # Use file_type from specification without index
                file_category = spec_name.split('_')[0]
                file_type = file_spec['file_type']
                file_extension = file_path.suffix.lower()

                # Check if file needs conversion warning
                if file_extension in warning_extensions:
                    case = invalid_case.get(spec_name, {})
                    case['warning'] = case.get('warning', []) + [file_extension]
                    warning_case[spec_name] = case
                    break

                if file_category in allowed_extensions.keys():
                    if file_extension in allowed_extensions[file_category]:
                        continue
                    else:
                        case = invalid_case.get(spec_name, {})
                        case['invalid'] = case.get('invalid', []) + [file_extension]
                        case['expected'] = allowed_extensions[file_category]
                        invalid_case[spec_name] = case
                        break

                if file_type in allowed_extensions.keys():
                    if file_extension in allowed_extensions[file_type]:
                        continue
                    else:
                        case = invalid_case.get(spec_name, {})
                        case['invalid'] = case.get('invalid', []) + [file_extension]
                        case['expected'] = allowed_extensions[file_category]
                        break

            if invalid_case or warning_case:
                all_violation_case[spec_name] = {
                    'invalid': invalid_case.get(spec_name, {}),
                    'warning': warning_case.get(spec_name, {}),
                }
                continue
            valid_files.append(file_group)

        # Display validation messages for all violations
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

        return valid_files
