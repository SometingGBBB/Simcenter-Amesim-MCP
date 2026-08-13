# Third-party notices

`amesim-mcp`'s own code (`amesim_mcp/`) is MIT-licensed — see [LICENSE](LICENSE).

The `vendor/` directory vendors pre-built copies of the following packages,
needed because the Amesim worker process runs inside `AMEPython.exe`, an
embedded Python 3.6 interpreter that has no `pip`/internet access. Each
keeps its own original license file in-tree; nothing here relicenses them.

| Package  | Version | License              | License file in this repo                         |
|----------|---------|-----------------------|-----------------------------------------------------|
| pywin32  | 305     | PSF-style (BSD-like)  | `vendor/win32/license.txt`, `vendor/win32com/License.txt`, `vendor/pythonwin/license.txt` |
| rpyc     | 5.0.1   | MIT                   | `vendor/rpyc-5.0.1.dist-info/LICENSE`               |
| plumbum  | 1.8.3   | MIT                   | `vendor/plumbum-1.8.3.dist-info/licenses/LICENSE`   |
| adodbapi | bundled | LGPL-2.1              | `vendor/adodbapi/license.txt`                       |

If you redistribute this repository (including the `vendor/` directory),
keep these license files alongside the code they cover.

"Simcenter Amesim" and "AMEPython" are products of Siemens Digital
Industries Software. This project is an independent, unofficial
integration and is not affiliated with, endorsed by, or sponsored by
Siemens.
