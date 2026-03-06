-- Use folder name to build extension name and tag. Version is specified explicitly.
local ext = get_current_extension_info()

project_ext (ext)

-- Link only those files and folders into the extension target directory
repo_build.prebuild_link {
    { "data", ext.target_dir.."/data" },
    { "docs", ext.target_dir.."/docs" },
    { "item_placement_system", ext.target_dir.."/item_placement_system" },
}