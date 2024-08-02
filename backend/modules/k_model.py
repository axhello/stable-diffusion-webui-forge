import torch

from backend import memory_management
from backend.modules.k_prediction import k_prediction_from_diffusers_scheduler


class KModel(torch.nn.Module):
    def __init__(self, huggingface_components, storage_dtype, computation_dtype):
        super().__init__()

        self.storage_dtype = storage_dtype
        self.computation_dtype = computation_dtype

        self.diffusion_model = huggingface_components['unet']
        self.prediction = k_prediction_from_diffusers_scheduler(huggingface_components['scheduler'])

    def apply_model(self, x, t, c_concat=None, c_crossattn=None, control=None, transformer_options={}, **kwargs):
        sigma = t
        xc = self.prediction.calculate_input(sigma, x)
        if c_concat is not None:
            xc = torch.cat([xc] + [c_concat], dim=1)

        context = c_crossattn
        dtype = self.computation_dtype

        xc = xc.to(dtype)
        t = self.prediction.timestep(t).float()
        context = context.to(dtype)
        extra_conds = {}
        for o in kwargs:
            extra = kwargs[o]
            if hasattr(extra, "dtype"):
                if extra.dtype != torch.int and extra.dtype != torch.long:
                    extra = extra.to(dtype)
            extra_conds[o] = extra

        model_output = self.diffusion_model(xc, t, context=context, control=control, transformer_options=transformer_options, **extra_conds).float()
        return self.prediction.calculate_denoised(sigma, model_output, x)

    def memory_required(self, input_shape):
        area = input_shape[0] * input_shape[2] * input_shape[3]
        dtype_size = memory_management.dtype_size(self.computation_dtype)

        scaler = 1.28

        # TODO: Consider these again
        # if ldm_patched.modules.model_management.xformers_enabled() or ldm_patched.modules.model_management.pytorch_attention_flash_attention():
        #     scaler = 1.28
        # else:
        #     scaler = 1.65
        #     if ldm_patched.ldm.modules.attention._ATTN_PRECISION == "fp32":
        #         dtype_size = 4

        return scaler * area * dtype_size * 16384
