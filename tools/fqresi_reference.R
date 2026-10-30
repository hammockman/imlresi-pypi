# Run FQResi createCorrArray on cases in a JSON file; used by fqresi_reference.py
args <- commandArgs(TRUE)
inp <- jsonlite::fromJSON(args[1], simplifyVector = FALSE)
if (args[3] != "installed") {
  # args[3]: a folder (next to the input) holding the FQResi R sources to use
  for (f in list.files(file.path(dirname(args[1]), args[3]), full.names = TRUE)) source(f)
  cca <- createCorrArray
} else {
  cca <- FQResi::createCorrArray
}
out <- lapply(inp, function(case) {
  r <- tryCatch(cca(as.numeric(unlist(case$drill)), case$sData, list(a = -0.786, b = 1), "xcheck"),
                error = function(e) paste("ERROR", conditionMessage(e)))
  r
})
writeLines(jsonlite::toJSON(out, digits = NA, auto_unbox = TRUE), args[2])
