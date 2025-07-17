{ pkgs }: {
  deps = [
    pkgs.python311Packages.flask
    pkgs.python311Packages.openpyxl
    pkgs.python311Packages.pandas
    pkgs.python311Packages.plotly
    pkgs.python311Packages.werkzeug
    pkgs.python311Packages.fpdf2
  ];
}