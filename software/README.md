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

We formulate the control problem as the following. Define the following variables $D, S, E$, the water demand, solar water supply, and electrically heated water supply, all in dimensions of volume of water per unit time. Note that the solar water supply will be delta functions, but we approximate it as a smooth curve. We also define the tank capacity as $X$

The constraint can then be formalized as $$\int_T \left[ {D}(t) - {S}(t) - {E}(t) \right] \, dt \leq X,$$ for all time intervals $T$.

And the optimization objective is to minimize the area under the curve of $E(t)$, since we assume a linear relationship between the amount of water heated electrically and energy consumed.

# Solar Availability Prediction
The solar availability module predicts future and current solar availability based on radiation intensity, temperature, and wind speed.

Use a fitted model to computes the time-to-60C. This model approximate the average power then use the formula for specific heat capacity to get `time-to-60C`. We predict average power to smooth out noise in ambient data.

This model employs a physics based model plus a linear residual for error correction.

$$ P_{ave} = \left[\eta A S_k - A (U_0 + k_v v_k)(T_k - T_{a,k})\right] + r_k$$

where

$$r_k = \beta_0 + \beta_1 S_k + \beta_2 v_k + \beta_3 (T_k - T_{a,k})$$

The residual error of the model $r_k$ will be corrected through fitting the coefficients $\beta _i$ with ground truth data.

So we derive that `time-to-60C = m * c_v * (60 - T_0) / P_ave`

# TODO
- [ ] Calculate the order of magnitude of `time-to-60C` to select a scale on which we select data to get $S_k$ and $T_k$