import pybullet as p

def get_revolute_joint_indices(body_id: int) -> list[int]:
    """Get indices of arm revolute joints (ignore fixed/prismatic gripper joints)."""
    revolute_indices = []
    num_joints = p.getNumJoints(body_id)
    
    for i in range(num_joints):
        joint_info = p.getJointInfo(body_id, i)
        joint_type = joint_info[2]
        
        if joint_type == p.JOINT_REVOLUTE:
            revolute_indices.append(i)
    
    return revolute_indices

def get_joint_name_map(body_id: int) -> dict[int, str]:
    """Map joint index to name"""
    name_map = {}
    num_joints = p.getNumJoints(body_id)
    
    for i in range(num_joints):
        joint_info = p.getJointInfo(body_id, i)
        joint_name = joint_info[1].decode('utf-8')
        name_map[i] = joint_name
    
    return name_map

def guess_end_effector_link(body_id: int, joint_indices: list[int]) -> int:
    """
    Heuristic to find end effector link index.
    Priority:
    1. Link name contains 'ee', 'eef', 'end', 'tool', 'tcp'
    2. Last revolute joint's child link
    """
    num_joints = p.getNumJoints(body_id)
    
    # Strategy 1: Search by name
    for i in range(num_joints):
        link_info = p.getJointInfo(body_id, i)
        link_name = link_info[12].decode('utf-8').lower()  # Link name
        
        if any(keyword in link_name for keyword in ['ee', 'eef', 'end', 'tool', 'tcp']):
            print(f"[DISCOVERY] Found EE link by name: {link_name} (index={i})")
            return i
    
    # Strategy 2: Use last revolute joint
    if joint_indices:
        last_joint = joint_indices[-1]
        print(f"[DISCOVERY] Using last revolute joint as EE: index={last_joint}")
        return last_joint
    
    # Fallback
    print(f"[DISCOVERY] WARNING: Using default EE link index={num_joints-1}")
    return num_joints - 1

def print_joint_table(body_id: int):
    """Print diagnostic table of all joints"""
    print("\n" + "="*80)
    print("JOINT TABLE")
    print("="*80)
    print(f"{'Index':<6} {'Name':<20} {'Type':<12} {'Lower':<8} {'Upper':<8}")
    print("-"*80)
    
    num_joints = p.getNumJoints(body_id)
    for i in range(num_joints):
        info = p.getJointInfo(body_id, i)
        name = info[1].decode('utf-8')
        joint_type = info[2]
        lower = info[8]
        upper = info[9]
        
        type_name = {
            p.JOINT_REVOLUTE: "REVOLUTE",
            p.JOINT_PRISMATIC: "PRISMATIC",
            p.JOINT_FIXED: "FIXED",
            p.JOINT_SPHERICAL: "SPHERICAL"
        }.get(joint_type, f"UNKNOWN({joint_type})")
        
        print(f"{i:<6} {name:<20} {type_name:<12} {lower:<8.2f} {upper:<8.2f}")
    
    print("="*80 + "\n")


def discover_gripper_joints(body_id: int) -> dict[str, int]:
    """Find gripper finger joint indices (prismatic finger joints)."""
    joints: dict[str, int] = {}
    num_joints = p.getNumJoints(body_id)
    for i in range(num_joints):
        info = p.getJointInfo(body_id, i)
        joint_name = info[1].decode("utf-8")
        joint_type = info[2]
        if "finger" in joint_name.lower() and joint_type == p.JOINT_PRISMATIC:
            joints[joint_name] = i
    return joints


def get_gripper_link_index(body_id: int, link_name: str = "gripper_base") -> int:
    """Return gripper link index by child-link name, or -1 if absent."""
    num_joints = p.getNumJoints(body_id)
    for i in range(num_joints):
        info = p.getJointInfo(body_id, i)
        child_link = info[12].decode("utf-8")
        if link_name in child_link:
            return i + 1
    return -1

