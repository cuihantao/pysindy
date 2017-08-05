import numpy as np

from sparsereg.model.ffx import FFX

np.random.seed(42)
x = np.random.normal(size=(1000, 2))
y = x[:, 0] / ( 1 + x[:, 1] )

model = FFX(n_jobs=-1)
model.fit(x, y)
print(model.print_model())