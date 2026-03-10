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


The solar availability module predicts future and current solar availability based on radiation intensity, temperature, and wind speed.