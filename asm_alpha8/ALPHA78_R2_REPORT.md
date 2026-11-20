# ASM v0.4.0-alpha.7.8 Experimental R2
R2 replaces inferred-pair reconstruction with a direct rank<=2 Woodbury factor-covariance solve. Latent weights remain source-wise capped by the wide covariance baseline, so hidden-factor inference cannot add routing confidence. Default routing remains alpha.7.7 `full_covariance` pending review.
