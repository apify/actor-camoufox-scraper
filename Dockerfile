# First, specify the base Docker image.
# You can see the Docker images from Apify at https://hub.docker.com/r/apify/.
# You can also use any other image from Docker Hub.
# Currently camoufox has issues installing on Python 3.13
FROM apify/actor-python-playwright:3.12
RUN apt install -yq git && rm -rf /var/lib/apt/lists/*

RUN pip install -U pip setuptools \
    && pip install 'poetry<2' \
    && poetry self add 'poetry-plugin-export<1.9.0'

# Second, copy just poetry.lock and pyproject.toml into the Actor image,
# since those should be the only files that affects the dependency install in the next step,
# in order to speed up the build
COPY pyproject.toml ./
COPY poetry.lock ./

# Install the dependencies
RUN echo "Python version:" \
 && python --version \
 && echo "Installing dependencies:" \
 # Export packages from poetry.lock
 && poetry export -f requirements.txt --without-hashes | \
 # Replace playwright version so that it matches whatever is pre-installed in the image
    sed "s/^playwright==.*/playwright==$(playwright --version | cut -d ' ' -f 2)/" | \
 # Install everything using pip (ignore dependency checks - the lockfile is correct, period)
    pip install -r /dev/stdin --no-dependencies \
 && echo "All installed Python packages:" \
 && pip freeze
# Next, copy the remaining files and directories with the source code.
# Since we do this after installing the dependencies, quick build will be really fast
# for most source file changes.
COPY . ./

# Use compileall to ensure the runnability of the Actor Python code.
RUN python -m compileall -q .

# Fetch camoufox files that are always needed when using camoufox.
RUN python -m camoufox fetch

# Specify how to launch the source code of your Actor.
CMD ["python", "-m", "template_test"]
