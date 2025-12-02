from pathlib import Path
from typing import Dict, List


class BaseUploader:
    """Base class for upload plugins with common functionality.

    This class handles common tasks like file organization, validation, and metadata
    that are shared across all upload plugins. Plugin developers should inherit
    from this class and implement the required methods for their specific logic.

    Important: Plugin extensions work with already-organized files from the main upload workflow.
    Whether single-path or multi-path mode is used is transparent to plugin developers - you
    simply process the organized_files list provided to you.

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

    Customization:
        To restrict file extensions, modify get_file_extensions_config() in this file:

        Example - Allow only MP4 videos:
            def get_file_extensions_config(self):
                return {
                    'video': ['.mp4'],  # Only MP4 allowed
                    'image': ['.jpg', '.png'],
                    # ... other types
                }
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
                  - In single-path mode: Base directory path (Path object)
                  - In multi-path mode: None (not needed - use self.assets_config instead)
                  Files have already been discovered from their respective asset paths.
            file_specification: List of specifications that define the structure of files to be uploaded.
            organized_files: List of pre-organized files based on the default logic.
                            Plugin extensions work with these already-organized files regardless of
                            whether single-path or multi-path mode was used.
            extra_params: Additional parameters for customization.
        """
        self.run = run
        self.path = path
        self.file_specification = file_specification or []
        self.organized_files = organized_files or []
        self.extra_params = extra_params or {}

    def get_file_extensions_config(self) -> Dict[str, List[str]]:
        """Get allowed file extensions configuration.

        Modify this dictionary to restrict file extensions per file type.
        Extensions are case-insensitive and must include the dot prefix.

        Example:
            To allow only MP4 videos::

                def get_file_extensions_config(self):
                    return {
                        'video': ['.mp4'],
                        'image': ['.jpg', '.png'],
                    }

        Returns:
            Dict[str, List[str]]: Mapping of file types to allowed extensions.
                Each key is a file type (e.g., 'video', 'image') and each value
                is a list of allowed extensions (e.g., ['.mp4', '.avi']).
        """
        # Configure allowed extensions here
        # Extensions should include the dot (e.g., '.mp4', not 'mp4')
        return {
            'video': ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv'],
            'image': ['.jpg', '.jpeg', '.png'],
            'pcd': ['.pcd'],
            'text': ['.txt', '.html'],
            'audio': ['.mp3', '.wav'],
            'data': ['.xml', '.bin', '.json', '.fbx'],
        }

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
        """Validate files against allowed extensions and custom rules.

        This method first validates file types against get_file_extensions_config(),
        then applies custom filtering via _filter_valid_files().

        Override this method for complete custom validation, or override
        _filter_valid_files() to add additional filtering after extension validation.
        """
        # First, validate file extensions
        files = self.validate_file_types(files)

        # Then apply custom filtering
        return self._filter_valid_files(files)

    def setup_directories(self) -> None:
        """Setup custom directories. Can be overridden by subclasses."""
        pass

    def validate_file_types(self, organized_files: List) -> List:
        """Validate file types against allowed extensions configuration.

        Filters files based on their extensions according to get_file_extensions_config().
        Files with extensions not matching their file type will be filtered out and logged.

        Args:
            organized_files (List[Dict]): List of organized file dictionaries.
                Each dict contains a 'files' key mapping spec names to file paths.

        Returns:
            List[Dict]: Filtered list containing only files with valid extensions.
                Files with disallowed extensions are removed and logged as WARNING.

        Note:
            Extension matching is case-insensitive (.mp4 == .MP4).
            Filtered files are logged using LogCode.FILES_FILTERED_BY_EXTENSION.
        """
        if not organized_files or not self.file_specification:
            return organized_files

        valid_files = []
        allowed_extensions_config = self.get_file_extensions_config()
        filtered_by_type = {}  # Track filtered files per type

        for file_group in organized_files:
            files_dict = file_group.get('files', {})
            is_valid_group = True

            for spec_name, file_path in files_dict.items():
                # Find the specification for this file type
                file_spec = next((s for s in self.file_specification if s['name'] == spec_name), None)
                if not file_spec:
                    continue

                # Handle file path lists
                if isinstance(file_path, list):
                    file_path = file_path[0] if file_path else None

                if file_path is None:
                    continue

                # Get file type and extension
                file_type = file_spec['file_type']
                file_extension = file_path.suffix.lower()

                # Check if this file type has allowed extensions
                if file_type in allowed_extensions_config:
                    allowed_exts = [ext.lower() for ext in allowed_extensions_config[file_type]]

                    if file_extension not in allowed_exts:
                        # Track filtered extension
                        if file_type not in filtered_by_type:
                            filtered_by_type[file_type] = {'extensions': set(), 'count': 0}
                        filtered_by_type[file_type]['extensions'].add(
                            file_extension if file_extension else '(no extension)'
                        )
                        filtered_by_type[file_type]['count'] += 1
                        is_valid_group = False
                        break

            # Add file group if all files are valid
            if is_valid_group:
                valid_files.append(file_group)

        # Log filtered files by type
        self._log_filtered_files(filtered_by_type, allowed_extensions_config)

        return valid_files

    def _log_filtered_files(self, filtered_by_type: Dict, allowed_config: Dict):
        """Log filtered files by type with detailed information.

        Args:
            filtered_by_type (Dict[str, Dict]): Filtered file information per type.
                Each entry contains 'extensions' (set) and 'count' (int).
            allowed_config (Dict[str, List[str]]): The allowed extensions configuration
                mapping file types to allowed extension lists.
        """
        from synapse_sdk.plugins.categories.upload.actions.upload.enums import LogCode

        for file_type, info in filtered_by_type.items():
            if info['count'] > 0:
                extensions_str = ', '.join(sorted(info['extensions']))
                allowed_str = ', '.join(allowed_config.get(file_type, []))
                self.run.log_message_with_code(
                    LogCode.FILES_FILTERED_BY_EXTENSION,
                    info['count'],
                    file_type,
                    extensions_str,
                    allowed_str,
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
