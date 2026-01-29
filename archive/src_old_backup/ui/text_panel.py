"""
Text panel formatter - consistent multiline panel rendering.
Week 9 Enhanced: Professional panel formatting for overlay.
"""

from typing import List, Tuple, Optional


class TextPanel:
    """
    Formatted text panel builder.
    
    Builds multiline strings with:
    - Header row with panel name
    - Optional border characters
    - Key-value pairs
    - Lists
    - Progress bars
    - Status indicators
    """
    
    def __init__(self, name: str, use_borders: bool = False):
        """
        Initialize panel.
        
        Args:
            name: Panel name (header)
            use_borders: If True, add ASCII borders
        """
        self.name = name
        self.use_borders = use_borders
        self.lines: List[str] = []
        
        # Add header
        if use_borders:
            self.lines.append(f"┌─ {name} " + "─" * (20 - len(name)))
        else:
            self.lines.append(f"[{name}]")
    
    def add_kv(self, key: str, value: str, width: int = 15) -> None:
        """
        Add key-value pair.
        
        Args:
            key: Key name
            value: Value string
            width: Width for key padding
        """
        # Pad key to consistent width
        padded_key = f"{key}:".ljust(width)
        self.lines.append(f"  {padded_key} {value}")
    
    def add_line(self, text: str) -> None:
        """
        Add plain text line.
        
        Args:
            text: Text content
        """
        self.lines.append(f"  {text}")
    
    def add_list(self, items: List[str], prefix: str = "•") -> None:
        """
        Add bulleted list.
        
        Args:
            items: List items
            prefix: Bullet character
        """
        for item in items:
            self.lines.append(f"  {prefix} {item}")
    
    def add_progress_bar(self, label: str, progress: float, width: int = 20) -> None:
        """
        Add progress bar.
        
        Args:
            label: Bar label
            progress: Progress 0.0-1.0
            width: Bar width in characters
        """
        filled = int(width * progress)
        bar = "█" * filled + "░" * (width - filled)
        pct = int(progress * 100)
        self.lines.append(f"  {label}: [{bar}] {pct}%")
    
    def add_status(self, label: str, status: bool, true_text: str = "✓", false_text: str = "✗") -> None:
        """
        Add status indicator.
        
        Args:
            label: Status label
            status: Boolean status
            true_text: Text for true status
            false_text: Text for false status
        """
        indicator = true_text if status else false_text
        self.lines.append(f"  {label}: {indicator}")
    
    def add_separator(self) -> None:
        """Add visual separator."""
        if self.use_borders:
            self.lines.append("  " + "─" * 30)
        else:
            self.lines.append("")
    
    def add_metric(self, label: str, value: float, unit: str = "", decimals: int = 1) -> None:
        """
        Add metric with formatting.
        
        Args:
            label: Metric label
            value: Numeric value
            unit: Optional unit string
            decimals: Decimal places
        """
        formatted = f"{value:.{decimals}f}"
        if unit:
            formatted += f" {unit}"
        self.add_kv(label, formatted)
    
    def add_warning(self, text: str) -> None:
        """
        Add warning line.
        
        Args:
            text: Warning message
        """
        self.lines.append(f"  ⚠️  {text}")
    
    def add_error(self, text: str) -> None:
        """
        Add error line.
        
        Args:
            text: Error message
        """
        self.lines.append(f"  ❌ {text}")
    
    def add_success(self, text: str) -> None:
        """
        Add success line.
        
        Args:
            text: Success message
        """
        self.lines.append(f"  ✓ {text}")
    
    def build(self) -> str:
        """
        Build final panel text.
        
        Returns:
            Formatted multiline string
        """
        if self.use_borders:
            # Close border
            self.lines.append("└" + "─" * 31)
        
        return "\n".join(self.lines)
    
    def get_line_count(self) -> int:
        """
        Get number of lines in panel.
        
        Returns:
            Line count
        """
        return len(self.lines)
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """
        Format duration in human-readable form.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted string (e.g., "2.5s", "1m 30s")
        """
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    
    @staticmethod
    def truncate(text: str, max_length: int = 30, suffix: str = "...") -> str:
        """
        Truncate text to maximum length.
        
        Args:
            text: Input text
            max_length: Maximum length
            suffix: Truncation suffix
            
        Returns:
            Truncated string
        """
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix




