"""Workspace UI - Main window with object display and visualizer."""

import tkinter as tk
from typing import Dict, Callable, Optional
import cv2
import numpy as np
from PIL import Image, ImageTk
from ui.intent_visualizer import IntentVisualizer
from ui.camera_overlay import CameraOverlay
from intent_core.schema import SystemState

class WorkspaceUI:
    """
    Main UI window (ENHANCED for Week 6)
    
    Now shows:
    - Camera feed with overlays (Week 1-2)
    - Affordances panel (Week 3)
    - Gesture status (Week 4)
    - World state (Week 5)
    - Undo availability (Week 5)
    - ENHANCED STATE VISUALIZATION (NEW - Week 6)
      - Emoji indicators for object states
      - Color-coded state display
      - Visual glow/gap effects for clarity
    """
    
    def __init__(self, title: str = "Intent Interface - Visual Demo", config: Optional[Dict] = None):
        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry("1400x700")
        
        # Configuration
        self.config = config or {}
        ui_config = self.config.get("ui", {})
        camera_config = self.config.get("camera_overlay", {})
        
        # Main container
        self.main_container = tk.Frame(self.root, bg="#2d2d2d")
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # LEFT: Workspace canvas
        self.canvas = tk.Canvas(
            self.main_container,
            width=900,
            height=700,
            bg="#2d2d2d",
            highlightthickness=0
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # RIGHT: Intent Visualizer
        self.visualizer = IntentVisualizer(self.main_container)
        
        # Camera overlay
        self.camera_overlay = CameraOverlay(camera_config)
        self.camera_canvas = None  # Tkinter label for camera feed
        
        # Store current snapshot
        self.current_snapshot = None
        
        # World state display (NEW - Week 5)
        self.world_objects_panel = None
        self.undo_panel = None
        self.object_widgets = {}
        
        self.setup_world_state_panel()
        self.setup_undo_panel()
    
    def update(self, ui_snapshot: Dict):
        """Update UI from snapshot."""
        self.current_snapshot = ui_snapshot
        
        # Clear canvas
        self.canvas.delete("all")
        
        # Render title
        self.canvas.create_text(
            450, 30,
            text="Intent Interface Prototype",
            font=("Arial", 24, "bold"),
            fill="#ffffff"
        )
        
        self.canvas.create_text(
            450, 60,
            text="Weeks 1-9 Complete System",
            font=("Arial", 14),
            fill="#999999"
        )
        
        # Render objects
        self._render_objects(ui_snapshot.get("world_objects", {}))
        
        # Render status
        self._render_status_bar(ui_snapshot)
        
        # Update visualizer
        self.visualizer.render(ui_snapshot)
        
        self.root.update()
    
    def _render_objects(self, world_objects: Dict):
        """Render world objects."""
        x_positions = {
            "obj_left": 250,
            "obj_center": 450,
            "obj_right": 650
        }
        
        y = 350
        
        for obj_id, obj_state in world_objects.items():
            x = x_positions.get(obj_id, 450)
            
            # Determine color
            toggled = obj_state.get("state", {}).get("toggled", False)
            locked_by = obj_state.get("locked_by")
            
            if toggled:
                fill_color = "#4CAF50"  # Green
            else:
                fill_color = "#2196F3"  # Blue
            
            outline_color = "#ffffff"
            outline_width = 2
            
            # Highlight if locked
            if locked_by:
                outline_color = "#ff6600"
                outline_width = 4
            
            # Draw square
            self.canvas.create_rectangle(
                x - 80, y - 80, x + 80, y + 80,
                fill=fill_color,
                outline=outline_color,
                width=outline_width,
                tags=obj_id
            )
            
            # Label
            label = obj_id.replace("obj_", "").replace("_", " ").title()
            self.canvas.create_text(
                x, y,
                text=label,
                font=("Arial", 18, "bold"),
                fill="white"
            )
            
            # Lock indicator
            if locked_by:
                self.canvas.create_text(
                    x, y + 100,
                    text=f"🔒 {locked_by}",
                    font=("Arial", 10),
                    fill="#ff6600"
                )
    
    def _render_status_bar(self, snapshot: Dict):
        """Render status bar at bottom."""
        status = snapshot.get("system_status", "UNKNOWN")
        
        self.canvas.create_text(
            450, 650,
            text=f"Status: {status}",
            font=("Arial", 16),
            fill="#ffffff"
        )
        
        why_nothing = snapshot.get("why_nothing_happened")
        if why_nothing:
            self.canvas.create_text(
                450, 675,
                text=f"→ {why_nothing}",
                font=("Arial", 12),
                fill="#ffaa00"
            )
    
    def setup_camera_display(self):
        """Add camera feed panel to UI."""
        if self.camera_canvas is None:
            # Create camera display panel (above workspace canvas)
            camera_frame = tk.Frame(self.main_container, bg="#1a1a1a")
            camera_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
            
            self.camera_canvas = tk.Label(
                camera_frame,
                bg="#000000",
                width=640,
                height=480
            )
            self.camera_canvas.pack()
    
    def update_camera_display(self, annotated_frame: np.ndarray):
        """
        Update camera feed with OpenCV -> Tkinter conversion.
        
        Args:
            annotated_frame: Annotated frame from camera overlay (BGR format)
        """
        if self.camera_canvas is None:
            return
        
        try:
            # Convert BGR -> RGB
            rgb_frame = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
            
            # Resize if needed (maintain aspect ratio)
            max_width = 640
            max_height = 480
            
            h, w = rgb_frame.shape[:2]
            if w > max_width or h > max_height:
                scale = min(max_width / w, max_height / h)
                new_w = int(w * scale)
                new_h = int(h * scale)
                rgb_frame = cv2.resize(rgb_frame, (new_w, new_h))
            
            # Convert to PIL Image
            pil_image = Image.fromarray(rgb_frame)
            
            # Convert to Tkinter PhotoImage
            tk_image = ImageTk.PhotoImage(pil_image)
            
            # Update canvas
            self.camera_canvas.configure(image=tk_image)
            self.camera_canvas.image = tk_image  # Keep reference
        except Exception as e:
            # Silently fail if camera display fails
            pass
    
    def render_camera_overlay(self,
                             frame: np.ndarray,
                             scope_signal: Optional[object],
                             detection_result: Optional[object],
                             system_state: SystemState) -> np.ndarray:
        """
        Render camera overlay on frame.
        
        Args:
            frame: Camera frame (BGR format)
            scope_signal: CameraScopeSignal (if any)
            detection_result: DetectionResult (if any)
            system_state: Current SystemState
            
        Returns:
            Annotated frame (BGR format)
        """
        return self.camera_overlay.render(frame, scope_signal, detection_result, system_state)
    
    def setup_world_state_panel(self):
        """
        Create world state visualization panel
        
        Shows simulated object states (lamp on/off, door open/closed, etc.)
        """
        panel = tk.Frame(self.root, bg='#1e1e1e', padx=20, pady=20)
        panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Header
        header = tk.Label(panel, text="WORLD STATE (SIMULATOR)",
                         font=('Arial', 14, 'bold'),
                         bg='#1e1e1e', fg='#00ff00')
        header.pack(anchor='w', pady=(0, 10))
        
        # Objects container
        self.world_objects_container = tk.Frame(panel, bg='#1e1e1e')
        self.world_objects_container.pack(fill=tk.BOTH, expand=True)
        
        # Object widgets (created dynamically)
        self.object_widgets = {}
        
        self.world_objects_panel = panel
    
    def setup_undo_panel(self):
        """
        Create undo availability panel
        
        Shows:
        - Whether undo is available
        - What action can be undone
        - Time remaining
        - Instructions
        """
        panel = tk.Frame(self.root, bg='#2b2b2b', padx=10, pady=10)
        panel.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Undo status label
        self.undo_status_label = tk.Label(panel, text="",
                                          font=('Arial', 11),
                                          bg='#2b2b2b', fg='#ffcc00')
        self.undo_status_label.pack(anchor='w')
        
        # Countdown label
        self.undo_countdown_label = tk.Label(panel, text="",
                                             font=('Courier', 10),
                                             bg='#2b2b2b', fg='#aaaaaa')
        self.undo_countdown_label.pack(anchor='w')
        
        self.undo_panel = panel
    
    def update_world_state(self, world_objects: dict):
        """
        Update world state visualization
        
        Args:
            world_objects: Dict of object_id -> WorldObjectState
        """
        for obj_id, obj_state in world_objects.items():
            if obj_id not in self.object_widgets:
                # Create new widget for this object
                self._create_object_widget(obj_id, obj_state)
            
            # Update existing widget
            self._update_object_widget(obj_id, obj_state)
    
    def _create_object_widget(self, obj_id: str, obj_state):
        """Create visual widget for an object"""
        widget_frame = tk.Frame(self.world_objects_container,
                               bg='#2b2b2b',
                               relief=tk.RAISED,
                               borderwidth=2,
                               padx=15, pady=15)
        widget_frame.pack(fill=tk.X, pady=5)
        
        # Object label
        label = tk.Label(widget_frame,
                        text=f"{obj_state.category.upper()} ({obj_id[-4:]})",
                        font=('Arial', 12, 'bold'),
                        bg='#2b2b2b', fg='white')
        label.pack(anchor='w')
        
        # State display
        state_label = tk.Label(widget_frame,
                              text="",
                              font=('Courier', 16, 'bold'),
                              bg='#2b2b2b', fg='#00ff00')
        state_label.pack(anchor='w', pady=(5, 0))
        
        # Visual indicator (colored square/circle)
        canvas = tk.Canvas(widget_frame, width=80, height=80,
                          bg='#2b2b2b', highlightthickness=0)
        canvas.pack(anchor='w', pady=(5, 0))
        
        # Store widget components
        self.object_widgets[obj_id] = {
            'frame': widget_frame,
            'label': label,
            'state_label': state_label,
            'canvas': canvas,
            'category': obj_state.category
        }
    
    def _update_object_widget(self, obj_id: str, obj_state):
        """Update object widget with current state (ENHANCED for Week 6)"""
        if obj_id not in self.object_widgets:
            return
        
        widget = self.object_widgets[obj_id]
        category = obj_state.category
        state = obj_state.state
        
        # Update based on category
        if category == 'lamp':
            power = state.get('power', 'off')
            
            # Enhanced label with visual indicator
            if power == 'on':
                state_emoji = "💡"
                state_text = "ON"
                state_color = '#ffff00'
            else:
                state_emoji = "🔌"
                state_text = "OFF"
                state_color = '#333333'
            
            widget['state_label'].config(
                text=f"{state_emoji} Power: {state_text}",
                fg=state_color
            )
            
            # Visual: bright yellow if on, dim gray if off
            canvas = widget['canvas']
            canvas.delete('all')
            
            # Glow effect when on
            if power == 'on':
                # Outer glow
                canvas.create_oval(5, 5, 75, 75, fill='#ffff88', outline='')
                # Inner bright
                canvas.create_oval(10, 10, 70, 70, fill='#ffff00', outline='white', width=3)
            else:
                # Dim bulb
                canvas.create_oval(10, 10, 70, 70, fill='#333333', outline='#666666', width=2)
        
        elif category == 'door':
            position = state.get('position', 'closed')
            
            if position == 'open':
                state_emoji = "🚪"
                state_text = "OPEN"
                state_color = '#00ff00'
            else:
                state_emoji = "🚪"
                state_text = "CLOSED"
                state_color = '#ff8800'
            
            widget['state_label'].config(
                text=f"{state_emoji} Position: {state_text}",
                fg=state_color
            )
            
            # Visual: gap when open, solid when closed
            canvas = widget['canvas']
            canvas.delete('all')
            
            if position == 'open':
                # Two panels with gap
                canvas.create_rectangle(10, 10, 30, 70, fill='#8B4513', outline='white', width=2)
                canvas.create_rectangle(50, 10, 70, 70, fill='#8B4513', outline='white', width=2)
                # Arrow indicating open
                canvas.create_text(40, 40, text="←→", font=('Arial', 16), fill='white')
            else:
                # Single closed door
                canvas.create_rectangle(10, 10, 70, 70, fill='#8B4513', outline='white', width=3)
                # Handle
                canvas.create_oval(60, 35, 65, 45, fill='#FFD700', outline='')
        
        elif category == 'phone':
            screen = state.get('screen', 'screen_off')
            
            if screen == 'screen_on':
                state_emoji = "📱"
                state_text = "SCREEN ON"
                state_color = '#00ff00'
            else:
                state_emoji = "📴"
                state_text = "SCREEN OFF"
                state_color = '#666666'
            
            widget['state_label'].config(
                text=f"{state_emoji} Screen: {state_text}",
                fg=state_color
            )
            
            # Visual: white screen if on, black if off
            canvas = widget['canvas']
            canvas.delete('all')
            
            # Phone outline
            canvas.create_rectangle(20, 5, 60, 75, fill='#000000', outline='#666666', width=3)
            
            if screen == 'screen_on':
                # White screen
                canvas.create_rectangle(22, 10, 58, 70, fill='#ffffff', outline='')
                # Notch
                canvas.create_rectangle(35, 7, 45, 10, fill='#000000', outline='')
            else:
                # Black screen
                canvas.create_rectangle(22, 10, 58, 70, fill='#0a0a0a', outline='')
    
    def update_undo_status(self, undo_info: Optional[dict]):
        """
        Update undo panel with current undo availability
        
        Args:
            undo_info: Dict with undo information or None
        """
        if undo_info is None or not undo_info.get('available'):
            # No undo available
            self.undo_status_label.config(
                text="Undo: Not available",
                fg='#666666'
            )
            self.undo_countdown_label.config(text="")
            return
        
        # Undo available
        action_label = undo_info.get('object_label', 'unknown')
        time_remaining = undo_info.get('time_remaining', 0)
        confirming = undo_info.get('confirming', False)
        
        if confirming:
            # In UNDO_CONFIRMING state
            self.undo_status_label.config(
                text=f"⚠️ UNDO CONFIRMING: {action_label}",
                fg='#ff8800'
            )
            self.undo_countdown_label.config(
                text=f"   Pinch to undo | {time_remaining:.1f}s remaining",
                fg='#ff8800'
            )
        else:
            # Undo available but not yet requested
            self.undo_status_label.config(
                text=f"✓ Undo available: {action_label}",
                fg='#00ff00'
            )
            self.undo_countdown_label.config(
                text=f"   Press 'U' to undo | {time_remaining:.1f}s remaining",
                fg='#aaaaaa'
            )
    
    def run(self, update_callback: Optional[Callable] = None, tick_ms: int = 500):
        """Run UI main loop."""
        def tick():
            if update_callback:
                update_callback(tick_ms / 1000.0)
            self.root.after(tick_ms, tick)
        
        if update_callback:
            tick()
        
        self.root.mainloop()

