{
  description = "A web GUI for configuring SteelSeries mice, built on rivalcfg";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = nixpkgs.lib.genAttrs systems;

      version = "0.0.0+${self.shortRev or "dirty"}";

      # nixpkgs ships rivalcfg as an application, so lift it back into a module
      # that python3.withPackages and buildPythonApplication can consume.
      overlay = final: prev: {
        rivalcfg-gui = final.python3Packages.buildPythonApplication {
          pname = "rivalcfg-gui";
          inherit version;
          src = ./.;
          pyproject = true;
          build-system = with final.python3Packages; [ setuptools setuptools-scm ];
          dependencies = [
            final.python3Packages.flask
            (final.python3Packages.toPythonModule final.rivalcfg)
          ];
          doCheck = false;
          meta = with final.lib; {
            description = "A web GUI for configuring SteelSeries mice";
            license = licenses.mit;
            mainProgram = "rivalcfg-gui";
            platforms = platforms.unix;
          };
        };
      };

      pkgsFor = system: import nixpkgs { inherit system; overlays = [ overlay ]; };
    in
    {
      overlays.default = overlay;

      packages = forAll (system: rec {
        rivalcfg-gui = (pkgsFor system).rivalcfg-gui;
        default = rivalcfg-gui;
      });

      devShells = forAll (system:
        let
          pkgs = pkgsFor system;
          python = pkgs.python3.withPackages (ps: [
            ps.flask
            ps.pytest
            ps.pyinstaller
            (ps.toPythonModule pkgs.rivalcfg)
          ]);
        in
        {
          default = pkgs.mkShell {
            packages = [ python pkgs.rivalcfg ];
            shellHook = ''
              echo "run:  python -m rivalcfg_gui --demo"
              echo "test: pytest -q"
            '';
          };
        });

      # Installs the app and the udev rules that let a normal user talk to the
      # mouse. You still need to be in the "input" group.
      nixosModules.default = { config, lib, pkgs, ... }:
        let cfg = config.programs.rivalcfg-gui;
        in {
          options.programs.rivalcfg-gui.enable =
            lib.mkEnableOption "the SteelSeries mouse configuration GUI";

          config = lib.mkIf cfg.enable {
            nixpkgs.overlays = [ overlay ];
            environment.systemPackages = [ pkgs.rivalcfg-gui pkgs.rivalcfg ];
            services.udev.packages = [ pkgs.rivalcfg ];
          };
        };
    };
}
