import mujoco

print(f"MuJoCo version: {mujoco.__version__}")

# Quick smoke test — load a built-in model
model = mujoco.MjModel.from_xml_string("""
<mujoco>
  <worldbody>
    <body>
      <joint type="hinge"/>
      <geom type="sphere" size="0.1"/>
    </body>
  </worldbody>
</mujoco>
""")
data = mujoco.MjData(model)
mujoco.mj_step(model, data)
print("MuJoCo smoke test PASSED")
