# ---------- Stage 1: Build Conda Environment ----------
FROM mcr.microsoft.com/azureml/curated/minimal-py312-cuda12.4-inference AS conda-env

USER root

# Copy only env.yml first (maximize build cache)
COPY docker/training/env/env.yml /tmp/env.yml

# The AzureML base already ships Conda. Create the environment at its final
# absolute path so it can be copied between stages without conda-pack.
RUN conda env create --prefix /opt/conda/envs/bda -f /tmp/env.yml \
	&& conda install --prefix /opt/conda/envs/bda -c conda-forge setuptools --force-reinstall -y \
	&& conda clean -afy


# ---------- Stage 2: Final Runtime Image ----------
FROM mcr.microsoft.com/azureml/curated/minimal-py312-cuda12.4-inference

USER root

# CLI shim for the building-embedding workflow (mirrors imageryprep's
# prepare-imagery shim). `python` resolves to the conda env at runtime via PATH.
RUN printf '#!/bin/bash\nexec python -m hastegeo.workflows.embed_buildings "$@"\n' > /usr/local/bin/embed-buildings \
	&& chmod +x /usr/local/bin/embed-buildings

# Preserve the environment's absolute prefix when copying it from the builder.
COPY --chown=dockeruser:dockeruser --from=conda-env /opt/conda/envs/bda /opt/conda/envs/bda
USER dockeruser

# Set working directory (created as dockeruser since USER is already set)
WORKDIR /app

# Copy application code and scripts with correct ownership at copy time
COPY --chown=dockeruser:dockeruser docker/training/code /app
COPY --chown=dockeruser:dockeruser docker/training/scripts/ /app/scripts/

# Copy haste source so training can import the package just like imagery prep
COPY --chown=dockeruser:dockeruser hastelib/src/hastegeo /app/hastegeo

# Convert line endings and ensure scripts are executable inside the container
USER root
RUN sed -i 's/\r$//' /app/scripts/*.sh && chmod +x /app/scripts/*.sh

# Activate the environment by default and expose shared data directories
ENV PATH="/opt/conda/envs/bda/bin:${PATH}"
ENV PROJ_LIB=/opt/conda/envs/bda/share/proj
ENV GDAL_DATA=/opt/conda/envs/bda/share/gdal
ENV PYTHONPATH=/app
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Refuse the GDAL drivers carrying the deferred CVEs (HDF4/HDF-EOS heap
# overflow CVE-2026-8087 et al.) at the GDAL level, so subprocess CLI tools
# (gdalwarp/gdal_translate) and the runtime never register them. In-process
# training step entrypoints additionally call hastegeo.core.utils.
# gdal_security.harden_gdal(). See docs/known-vulnerabilities.md Root Cause C.
ENV GDAL_SKIP="HDF4 HDF4Image HDF5 HDF5Image netCDF"


# Pre-bake DINOv2 source + weights into an image-level torch.hub cache so
# Azure Batch nodes don't need internet access (or the GitHub API) at job
# runtime. The workflow code calls ``torch.hub.set_dir(TORCH_HUB_CACHE_DIR)``
# before loading so this cache is used regardless of the per-task TORCH_HOME
# the entrypoint script sets. Must run after the SSL_CERT_FILE env block so
# the conda Python trusts GitHub's TLS cert for the source-repo fetch.
RUN mkdir -p /opt/torch-hub-cache/hub \
	&& chown -R dockeruser:dockeruser /opt/torch-hub-cache
USER dockeruser
RUN python -c "import torch; torch.hub.set_dir('/opt/torch-hub-cache/hub'); \
	torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14', trust_repo=True); \
	torch.hub.load('facebookresearch/dinov2', 'dinov2_vitb14', trust_repo=True)"

# Use training-specific entrypoint wrapper to mirror imagery prep behavior
ENTRYPOINT ["/app/scripts/entrypoint.sh"]