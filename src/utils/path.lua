local path = {}

-- Copyright 2011-2014, Gianluca Fiore © <forod.g@gmail.com>

--- Function equivalent to dirname in POSIX systems
--@param str the path string
function path.dirname(str)
    if str:match(".-/.-") then
        local name = string.gsub(str, "(.*/)(.*)", "%1")
        return name
    else
        return ''
    end
end

return path
