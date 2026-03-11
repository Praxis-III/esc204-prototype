# Control System
There are three major controlled variables `solar_availablity`, `tank_state`, and `water_demand`.

- Constraint is that fulfill demand at all times
- Optimization objective is to use minimal electrical energy


We also define constants in `config.xml`. The total volume of the tank, the daily demand curve, the time-to-60C as a function of `f(temperature, radiation, wind)`.

The output of the control are the flags `refill_water` and `activate_heater`.


- `refill_water` empties the PVT when solar is available.
- `refill_water` fills tank according to demand when solar is unavailable.
- `activate_heater` will be proxied with LED signals. 
    - Energy consumed will be modeled
    - Water will be heated to corresponding temperature in a set time.

---
# Solar Availability Prediction
The solar availability module predicts future and current solar availability based on radiation intensity, temperature, and wind speed.

-[] Requires calculation
*How can we use photoresistor when we have radiation forecast already?*
    - Maybe use it when internet unavailable

Use a model to correct the time-to-60C. 
Physics model + linear

$$\[ P_{ave} = \left[\eta A S_k - A (U_0 + k_v v_k)(T_k - T_{a,k})\right] + r_k\]$$

where

$$\[r_k = \beta_0 + \beta_1 S_k + \beta_2 v_k + \beta_3 (T_k - T_{a,k})\]$$

So we derive that `time-to-60C = mc_v / P_{ave}`